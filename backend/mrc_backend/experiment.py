from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
import csv
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import threading
import time
import traceback
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from .config import AppConfig
from .events import EventBus
from .hardware.camera import BaseCamera, CameraStatus, build_camera
from .hardware.daq import BaseDaq, DaqError, DaqStatus, TriggerDetector, build_daq


@dataclass
class ExperimentStatus:
    state: str = "idle"
    recording_mode: str = "trigger"
    session_id: Optional[str] = None
    output_dir: Optional[str] = None
    video_file: Optional[str] = None
    video_file2: Optional[str] = None
    aligned_video_file: Optional[str] = None
    aligned_video_file2: Optional[str] = None
    video_trim_status: Optional[str] = None
    trigger_count: int = 0
    started_at: Optional[str] = None
    first_trigger_at: Optional[str] = None
    elapsed_seconds: float = 0.0
    window_remaining_seconds: Optional[float] = None
    last_error: Optional[str] = None
    camera: Optional[Dict[str, Any]] = None
    camera2: Optional[Dict[str, Any]] = None
    daq: Optional[Dict[str, Any]] = None
    sync_timebase: str = "daq_sample_clock"
    t0_locked: bool = False
    expected_total_frames: Optional[int] = None
    video_t0_frame_estimated: Optional[int] = None
    usable_video_frame_start: Optional[int] = None
    usable_video_frame_end: Optional[int] = None
    preroll_seconds: Optional[float] = None
    stop_overshoot_samples: Optional[int] = None
    alignment_file: Optional[str] = None
    frame_map_file: Optional[str] = None


@dataclass
class SyncStartContext:
    camera_start_call_enter_monotonic_ns: int
    camera_recording_started_monotonic_ns: int
    daq_sample0_monotonic_ns: int
    camera2_start_call_enter_monotonic_ns: Optional[int] = None
    camera2_recording_started_monotonic_ns: Optional[int] = None


class ExperimentCoordinator:
    def __init__(self, config: AppConfig, repo_root: Path, event_bus: EventBus) -> None:
        self.config = config
        self.repo_root = repo_root
        self.event_bus = event_bus
        self.camera: BaseCamera = build_camera(config.hardware_mode, config.camera, repo_root)
        self.camera2: Optional[BaseCamera] = (
            build_camera(config.hardware_mode, config.camera2, repo_root)
            if config.camera2_enabled
            else None
        )
        self.daq: BaseDaq = build_daq(config.hardware_mode, config.daq, repo_root)
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._preview_stop_event = threading.Event()
        self._preview_worker: Optional[threading.Thread] = None
        self._subproc_lock = threading.Lock()
        self._active_subprocs: Set[subprocess.Popen] = set()
        # Camera ids that were successfully initialized at least once; only
        # these are auto-reconnected when their preview starts failing.
        self._camera_desired: Set[int] = set()
        self._status = ExperimentStatus(
            camera=asdict(self.camera.status()),
            camera2=asdict(self.camera2.status()) if self.camera2 else None,
            daq=asdict(self.daq.status()),
        )
        self._logger = logging.getLogger("mrc_backend.experiment")

    _ACTIVE_STATES = {"armed", "recording", "finalizing", "manual_recording"}
    _RECONNECT_FAILURE_THRESHOLD = 10
    _RECONNECT_COOLDOWN_SECONDS = 10.0
    _DAQ_RECOVERY_ATTEMPTS = 3
    _DAQ_RECOVERY_WAIT_SECONDS = 2.0

    def initialize(self) -> ExperimentStatus:
        with self._lock:
            if self._status.state in self._ACTIVE_STATES:
                raise RuntimeError("Cannot re-initialize hardware while an experiment is running.")
            camera_status = self.camera.initialize()
            self._camera_desired.add(1)
            camera2_status = None
            if self.camera2:
                camera2_status = self.camera2.initialize()
                self._camera_desired.add(2)
            daq_status = self.daq.initialize()
            self._status.camera = asdict(camera_status)
            self._status.camera2 = asdict(camera2_status) if camera2_status else None
            self._status.daq = asdict(daq_status)
            self._status.last_error = None
            self._ensure_preview_worker_locked()
        self.event_bus.publish("status", self.status_dict())
        return self.status()

    def devices(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "hardware_mode": self.config.hardware_mode,
                "camera": asdict(self.camera.status()),
                "camera2_enabled": self.camera2 is not None,
                "camera2": asdict(self.camera2.status()) if self.camera2 else None,
                "daq": asdict(self.daq.status()),
            }

    def diagnostics(self) -> Dict[str, Any]:
        with self._lock:
            if self._status.state in self._ACTIVE_STATES:
                result = {
                    "hardware_mode": self.config.hardware_mode,
                    "error": "Hardware diagnostics are unavailable while an experiment is running.",
                    "state": self._status.state,
                }
                return result
        result: Dict[str, Any] = {
            "hardware_mode": self.config.hardware_mode,
            "camera": {
                "ok": False,
                "status": asdict(self.camera.status()),
                "devices": [],
                "error": None,
            },
            "camera2_enabled": self.camera2 is not None,
            "camera2": None,
            "daq": {"ok": False, "status": asdict(self.daq.status()), "error": None},
        }
        if self.camera2 is not None:
            result["camera2"] = {
                "ok": False,
                "status": asdict(self.camera2.status()),
                "devices": [],
                "error": None,
            }
        try:
            enumerate_devices = getattr(self.camera, "enumerate_devices")
            result["camera"]["devices"] = enumerate_devices()
        except Exception as exc:  # noqa: BLE001
            result["camera"]["devices_error"] = str(exc)

        try:
            result["camera"]["status"] = asdict(self.camera.initialize())
            result["camera"]["ok"] = True
            self._camera_desired.add(1)
        except Exception as exc:  # noqa: BLE001
            result["camera"]["status"] = asdict(self.camera.status())
            result["camera"]["error"] = str(exc)

        if self.camera2 is not None:
            try:
                enumerate_devices2 = getattr(self.camera2, "enumerate_devices")
                result["camera2"]["devices"] = enumerate_devices2()
            except Exception as exc:  # noqa: BLE001
                result["camera2"]["devices_error"] = str(exc)

            try:
                result["camera2"]["status"] = asdict(self.camera2.initialize())
                result["camera2"]["ok"] = True
                self._camera_desired.add(2)
            except Exception as exc:  # noqa: BLE001
                result["camera2"]["status"] = asdict(self.camera2.status())
                result["camera2"]["error"] = str(exc)

        try:
            result["daq"]["status"] = asdict(self.daq.initialize())
            result["daq"]["ok"] = True
        except Exception as exc:  # noqa: BLE001
            result["daq"]["status"] = asdict(self.daq.status())
            result["daq"]["error"] = str(exc)

        self.event_bus.publish("diagnostics", result)
        return result

    def start_experiment(
        self,
        output_root: Optional[str] = None,
        window_minutes: Optional[float] = None,
        camera_fps: Optional[float] = None,
        threshold_volts: Optional[float] = None,
    ) -> ExperimentStatus:
        with self._lock:
            if self._status.state in self._ACTIVE_STATES:
                raise RuntimeError("Experiment is already running.")
            if camera_fps is not None:
                self.config.camera.fps = float(camera_fps)
            if threshold_volts is not None:
                self.config.daq.threshold_volts = float(threshold_volts)
            if window_minutes is not None:
                self.config.window_minutes = float(window_minutes)
            root = Path(output_root or self.config.output_root)
            if not root.is_absolute():
                root = (self.repo_root / root).resolve()
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
            output_dir = root / session_id
            output_dir.mkdir(parents=True, exist_ok=True)
            self.config.write_snapshot(output_dir / "config_snapshot.json")
            (output_dir / "events.jsonl").write_text("", encoding="utf-8")
            video_suffix = ".avi" if self.config.camera.capture_format == 1 else ".mp4"
            video_file = output_dir / f"mrc_recording{video_suffix}"
            video_suffix2 = ".avi" if self.config.camera2.capture_format == 1 else ".mp4"
            video_file2 = output_dir / f"mrc_recording_camera2{video_suffix2}"

            camera_start_call_enter_monotonic_ns = time.monotonic_ns()
            camera_status: CameraStatus
            camera2_status: Optional[CameraStatus] = None
            active_video_file: Path
            active_video_file2: Optional[Path] = None
            camera2_start_call_enter_monotonic_ns: Optional[int] = None
            camera2_recording_started_monotonic_ns: Optional[int] = None
            try:
                camera_status = self.camera.start_recording(video_file)
                active_video_file = Path(camera_status.active_file or str(video_file))
                camera_recording_started_monotonic_ns = time.monotonic_ns()
                if self.camera2 is not None:
                    camera2_start_call_enter_monotonic_ns = time.monotonic_ns()
                    camera2_status = self.camera2.start_recording(video_file2)
                    active_video_file2 = Path(camera2_status.active_file or str(video_file2))
                    camera2_recording_started_monotonic_ns = time.monotonic_ns()
            except Exception:
                self._stop_all_cameras()
                raise
            try:
                daq_status = self.daq.start_sampling()
            except Exception as first_exc:  # noqa: BLE001
                self._logger.warning("DAQ start failed (%s); retrying once after reconnect.", first_exc)
                try:
                    self.daq.reconnect()
                    daq_status = self.daq.start_sampling()
                except Exception:
                    # Don't leave the cameras recording with no experiment.
                    try:
                        self._stop_all_cameras()
                    except Exception as stop_exc:  # noqa: BLE001
                        self._logger.warning("Camera stop after DAQ start failure failed: %s", stop_exc)
                    raise
            daq_sample0_monotonic_ns = daq_status.sample0_monotonic_ns or time.monotonic_ns()
            sync_context = SyncStartContext(
                camera_start_call_enter_monotonic_ns=camera_start_call_enter_monotonic_ns,
                camera_recording_started_monotonic_ns=camera_recording_started_monotonic_ns,
                daq_sample0_monotonic_ns=daq_sample0_monotonic_ns,
                camera2_start_call_enter_monotonic_ns=camera2_start_call_enter_monotonic_ns,
                camera2_recording_started_monotonic_ns=camera2_recording_started_monotonic_ns,
            )
            self._stop_event.clear()
            self._status = ExperimentStatus(
                state="armed",
                recording_mode="trigger",
                session_id=session_id,
                output_dir=str(output_dir),
                video_file=str(active_video_file),
                video_file2=str(active_video_file2) if active_video_file2 else None,
                trigger_count=0,
                started_at=datetime.now().isoformat(timespec="milliseconds"),
                camera=asdict(camera_status),
                camera2=asdict(camera2_status) if camera2_status else None,
                daq=asdict(self.daq.status()),
                alignment_file=str(output_dir / "alignment.json"),
                frame_map_file=str(output_dir / "frame_map.csv"),
            )
            self._worker = threading.Thread(
                target=self._acquisition_loop,
                args=(output_dir, sync_context),
                name="mrc-acquisition",
                daemon=True,
            )
            self._worker.start()
        self.event_bus.publish("status", self.status_dict())
        return self.status()

    def start_manual_recording(
        self,
        output_root: Optional[str] = None,
        camera_fps: Optional[float] = None,
    ) -> ExperimentStatus:
        with self._lock:
            if self._status.state in self._ACTIVE_STATES:
                raise RuntimeError("Experiment is already running.")
            if camera_fps is not None:
                self.config.camera.fps = float(camera_fps)
            root = Path(output_root or self.config.output_root)
            if not root.is_absolute():
                root = (self.repo_root / root).resolve()
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
            output_dir = root / session_id
            output_dir.mkdir(parents=True, exist_ok=True)
            self.config.write_snapshot(output_dir / "config_snapshot.json")
            events_path = output_dir / "events.jsonl"
            events_path.write_text("", encoding="utf-8")
            video_suffix = ".avi" if self.config.camera.capture_format == 1 else ".mp4"
            video_file = output_dir / f"manual_recording{video_suffix}"
            video_suffix2 = ".avi" if self.config.camera2.capture_format == 1 else ".mp4"
            video_file2 = output_dir / f"manual_recording_camera2{video_suffix2}"

            camera2_status: Optional[CameraStatus] = None
            active_video_file2: Optional[Path] = None
            try:
                camera_status = self.camera.start_recording(video_file)
                active_video_file = Path(camera_status.active_file or str(video_file))
                if self.camera2 is not None:
                    camera2_status = self.camera2.start_recording(video_file2)
                    active_video_file2 = Path(camera2_status.active_file or str(video_file2))
            except Exception:
                self._stop_all_cameras()
                raise
            self._status = ExperimentStatus(
                state="manual_recording",
                recording_mode="manual",
                session_id=session_id,
                output_dir=str(output_dir),
                video_file=str(active_video_file),
                video_file2=str(active_video_file2) if active_video_file2 else None,
                started_at=datetime.now().isoformat(timespec="milliseconds"),
                camera=asdict(camera_status),
                camera2=asdict(camera2_status) if camera2_status else None,
                daq=asdict(self.daq.status()),
            )
            self._append_jsonl(
                events_path,
                {
                    "type": "manual_recording_started",
                    "payload": {
                        "video_file": str(active_video_file),
                        "video_file2": str(active_video_file2) if active_video_file2 else None,
                        "started_at": self._status.started_at,
                    },
                },
            )
        self.event_bus.publish("status", self.status_dict())
        return self.status()

    def stop_experiment(self) -> ExperimentStatus:
        worker: Optional[threading.Thread]
        with self._lock:
            worker = self._worker
            self._stop_event.set()
        if worker is not None and worker.is_alive():
            worker.join(timeout=5.0)
        with self._lock:
            if self._status.state in {"armed", "recording"}:
                self._set_finished_locked("stopped")
            elif self._status.state == "manual_recording":
                try:
                    self._stop_all_cameras()
                except Exception as exc:  # noqa: BLE001
                    self._logger.warning("Camera stop for manual recording failed: %s", exc)
                    self._status.last_error = str(exc)
                self._status.state = "manual_stopped"
                self._status.camera = asdict(self.camera.status())
                self._status.camera2 = asdict(self.camera2.status()) if self.camera2 else None
                self._status.daq = asdict(self.daq.status())
        self.event_bus.publish("status", self.status_dict())
        return self.status()

    def status(self) -> ExperimentStatus:
        with self._lock:
            return replace(self._status)

    def status_dict(self) -> Dict[str, Any]:
        return asdict(self.status())

    def close(self) -> None:
        self.stop_experiment()
        self._preview_stop_event.set()
        if self._preview_worker is not None and self._preview_worker.is_alive():
            self._preview_worker.join(timeout=2.0)
        self._kill_tracked_subprocesses()
        self.daq.close()
        self.camera.close()
        if self.camera2 is not None:
            self.camera2.close()

    def close_with_deadline(self, timeout_seconds: float = 4.0) -> None:
        done = threading.Event()

        def close_target() -> None:
            try:
                self.close()
            except Exception as exc:  # noqa: BLE001
                self._logger.warning("Coordinator shutdown cleanup failed: %s", exc)
            finally:
                done.set()

        cleanup_thread = threading.Thread(
            target=close_target,
            name="mrc-shutdown-cleanup",
            daemon=True,
        )
        cleanup_thread.start()
        cleanup_thread.join(timeout=max(0.5, timeout_seconds))
        if not done.is_set():
            self._logger.error(
                "Coordinator shutdown exceeded %.1fs; forcing Python process exit to release backend port.",
                timeout_seconds,
            )
            os._exit(0)

    def close_fast_without_sdk_teardown(self) -> None:
        self._logger.warning("Fast backend shutdown requested; skipping camera SDK teardown.")
        self._stop_event.set()
        self._preview_stop_event.set()
        with self._lock:
            worker = self._worker
        if worker is not None and worker.is_alive():
            # Let the acquisition thread leave its current DAQ read before we
            # close the device; closing while a read is in flight can wedge
            # the vendor driver in kernel mode and make the process unkillable.
            worker.join(timeout=2.0)
        # os._exit skips normal child reaping, so make sure no ffmpeg/ffprobe
        # is left behind holding the output files.
        self._kill_tracked_subprocesses()
        try:
            self.daq.close()
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("DAQ cleanup during fast shutdown failed: %s", exc)

    def _ensure_preview_worker_locked(self) -> None:
        if self._preview_worker is not None and self._preview_worker.is_alive():
            return
        self._preview_stop_event.clear()
        self._preview_worker = threading.Thread(
            target=self._preview_loop,
            name="mrc-preview",
            daemon=True,
        )
        self._preview_worker.start()

    def _preview_loop(self) -> None:
        last_error_message: Dict[int, str] = {}
        last_error_at: Dict[int, float] = {}
        consecutive_failures: Dict[int, int] = {}
        last_reconnect_at: Dict[int, float] = {}
        while not self._preview_stop_event.is_set():
            preview_fps = self._effective_preview_fps()
            interval_seconds = 1.0 / preview_fps
            started_at = time.monotonic()
            with self._lock:
                state_active = self._status.state in self._ACTIVE_STATES
            for camera_id, camera in self._iter_cameras():
                try:
                    frame = camera.preview_frame_data_url()
                    if frame:
                        consecutive_failures[camera_id] = 0
                        camera_status = camera.status()
                        self.event_bus.publish(
                            "preview",
                            {
                                "camera_id": camera_id,
                                "src": frame,
                                "mode": camera_status.mode,
                                "recording": camera_status.recording,
                                "fps": preview_fps,
                            },
                        )
                        last_error_message[camera_id] = ""
                except Exception as exc:  # noqa: BLE001
                    message = str(exc)
                    now = time.monotonic()
                    consecutive_failures[camera_id] = consecutive_failures.get(camera_id, 0) + 1
                    if message != last_error_message.get(camera_id) or now - last_error_at.get(camera_id, 0.0) >= 1.0:
                        self.event_bus.publish("preview_error", {"camera_id": camera_id, "message": message})
                        last_error_message[camera_id] = message
                        last_error_at[camera_id] = now
                    # Reconnect only outside active recordings: restarting a
                    # camera mid-run would invalidate the t0 alignment.
                    if (
                        camera_id in self._camera_desired
                        and not state_active
                        and consecutive_failures[camera_id] >= self._RECONNECT_FAILURE_THRESHOLD
                        and now - last_reconnect_at.get(camera_id, -self._RECONNECT_COOLDOWN_SECONDS)
                        >= self._RECONNECT_COOLDOWN_SECONDS
                        and not self._preview_stop_event.is_set()
                    ):
                        last_reconnect_at[camera_id] = now
                        if self._try_reconnect_camera(camera_id, camera):
                            consecutive_failures[camera_id] = 0
            elapsed_seconds = time.monotonic() - started_at
            self._preview_stop_event.wait(max(0.0, interval_seconds - elapsed_seconds))

    def _try_reconnect_camera(self, camera_id: int, camera: BaseCamera) -> bool:
        label = f"camera{camera_id}"
        self._logger.warning("Camera %d preview keeps failing; attempting automatic reconnect.", camera_id)
        self.event_bus.publish("reconnect", {"device": label, "status": "attempting"})
        try:
            status = camera.reconnect()
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Automatic reconnect for camera %d failed: %s", camera_id, exc)
            self.event_bus.publish("reconnect", {"device": label, "status": "failed", "message": str(exc)})
            return False
        with self._lock:
            if camera_id == 1:
                self._status.camera = asdict(status)
            else:
                self._status.camera2 = asdict(status)
        self._logger.info("Camera %d reconnected.", camera_id)
        self.event_bus.publish("reconnect", {"device": label, "status": "ok"})
        self.event_bus.publish("status", self.status_dict())
        return True

    def _attempt_daq_recovery(self) -> None:
        for attempt in range(1, self._DAQ_RECOVERY_ATTEMPTS + 1):
            if self._preview_stop_event.is_set():
                return
            self.event_bus.publish("reconnect", {"device": "daq", "status": "attempting", "attempt": attempt})
            try:
                status = self.daq.reconnect()
            except Exception as exc:  # noqa: BLE001
                self._logger.warning("DAQ automatic reconnect attempt %d failed: %s", attempt, exc)
                self.event_bus.publish(
                    "reconnect",
                    {"device": "daq", "status": "failed", "attempt": attempt, "message": str(exc)},
                )
                if self._preview_stop_event.wait(self._DAQ_RECOVERY_WAIT_SECONDS):
                    return
                continue
            with self._lock:
                self._status.daq = asdict(status)
            self._logger.info("DAQ reconnected on attempt %d.", attempt)
            self.event_bus.publish("reconnect", {"device": "daq", "status": "ok", "attempt": attempt})
            self.event_bus.publish("status", self.status_dict())
            return

    def _effective_preview_fps(self) -> float:
        configured_preview_fps = float(self.config.camera.preview_fps)
        if configured_preview_fps > 0:
            return max(1.0, min(60.0, configured_preview_fps))
        camera_status = self.camera.status()
        capture_fps = float(camera_status.fps or self.config.camera.fps)
        return max(1.0, min(60.0, capture_fps))

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._status.state = "error"
            self._status.last_error = message
            self._status.camera = asdict(self.camera.status())
            self._status.camera2 = asdict(self.camera2.status()) if self.camera2 else None
            self._status.daq = asdict(self.daq.status())
        self.event_bus.publish("error", {"message": message})
        self.event_bus.publish("status", self.status_dict())

    def _set_finished_locked(self, state: str = "finished") -> None:
        # Never let hardware teardown failures escape: an exception here would
        # leave the state machine stuck in "recording" with no way to recover
        # short of restarting the backend.
        try:
            self.daq.stop_sampling()
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("DAQ stop while finishing failed: %s", exc)
            self._status.last_error = str(exc)
        try:
            self._stop_all_cameras()
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Camera stop while finishing failed: %s", exc)
            self._status.last_error = str(exc)
        self._status.state = state
        self._status.camera = asdict(self.camera.status())
        self._status.camera2 = asdict(self.camera2.status()) if self.camera2 else None
        self._status.daq = asdict(self.daq.status())
        self._worker = None

    def _finalize_trigger_capture_locked(self, state: str = "finalizing") -> None:
        self.daq.stop_sampling()
        self._status.state = state
        self._status.camera = asdict(self.camera.status())
        self._status.camera2 = asdict(self.camera2.status()) if self.camera2 else None
        self._status.daq = asdict(self.daq.status())

    def _stop_camera_after_post_window_buffer(self) -> None:
        buffer_seconds = max(0.0, float(self.config.post_window_record_seconds))
        deadline = time.monotonic() + buffer_seconds
        while time.monotonic() < deadline and not self._stop_event.is_set():
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        self._stop_all_cameras()
        with self._lock:
            self._status.camera = asdict(self.camera.status())
            self._status.camera2 = asdict(self.camera2.status()) if self.camera2 else None

    def _run_tracked(self, command: List[str], timeout: float) -> subprocess.CompletedProcess:
        """Run an external tool while keeping a handle so shutdown can kill it."""
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        with self._subproc_lock:
            self._active_subprocs.add(proc)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise
        finally:
            with self._subproc_lock:
                self._active_subprocs.discard(proc)
        return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)

    def _kill_tracked_subprocesses(self) -> None:
        with self._subproc_lock:
            procs = list(self._active_subprocs)
        for proc in procs:
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass

    def _iter_cameras(self) -> List[tuple[int, BaseCamera]]:
        cameras: List[tuple[int, BaseCamera]] = [(1, self.camera)]
        if self.camera2 is not None:
            cameras.append((2, self.camera2))
        return cameras

    def _stop_all_cameras(self) -> None:
        first_error: Optional[Exception] = None
        for _camera_id, camera in self._iter_cameras():
            try:
                camera.stop_recording()
            except Exception as exc:  # noqa: BLE001
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error

    def _acquisition_loop(self, output_dir: Path, sync_context: SyncStartContext) -> None:
        trigger_csv = output_dir / "triggers.csv"
        db_path = output_dir / "triggers.sqlite3"
        events_path = output_dir / "events.jsonl"
        alignment_path = output_dir / "alignment.json"
        frame_map_path = output_dir / "frame_map.csv"
        detector = TriggerDetector(
            threshold=self.config.daq.threshold_volts,
            debounce_seconds=self.config.daq.debounce_seconds,
            sample_rate_hz=self.config.daq.sample_rate_hz,
        )
        global_sample = 0
        first_trigger_sample: Optional[int] = None
        target_end_sample: Optional[int] = None
        alignment: Optional[Dict[str, Any]] = None

        try:
            with trigger_csv.open("w", newline="", encoding="utf-8") as csv_file, sqlite3.connect(db_path) as db:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=[
                        "trigger_index",
                        "absolute_time",
                        "relative_time_seconds",
                        "sample_number",
                        "frame_index",
                        "window_remaining",
                        "frame_mapping_mode",
                        "sample_offset_from_t0",
                        "frame_index_from_t0",
                        "video_frame_index_estimated",
                        "timebase",
                    ],
                )
                writer.writeheader()
                db.execute(
                    """
                    create table if not exists triggers (
                        trigger_index integer primary key,
                        absolute_time text not null,
                        relative_time_seconds real not null,
                        sample_number integer not null,
                        frame_index integer not null,
                        window_remaining real not null,
                        frame_mapping_mode text not null,
                        sample_offset_from_t0 integer not null,
                        frame_index_from_t0 integer not null,
                        video_frame_index_estimated integer not null,
                        timebase text not null
                    )
                    """
                )
                db.commit()

                while not self._stop_event.is_set():
                    samples = self.daq.read_batch()
                    batch_start = global_sample
                    global_sample += len(samples)
                    detections = detector.process(samples, batch_start)
                    self._publish_waveform(samples, global_sample)

                    for detection in detections:
                        now = datetime.now()
                        if first_trigger_sample is None:
                            first_trigger_sample = detection.sample_number
                            alignment = self._build_alignment_metadata(
                                sync_context=sync_context,
                                t0_sample_number=first_trigger_sample,
                                output_dir=output_dir,
                            )
                            target_end_sample = int(alignment["target_end_sample"])
                            self._write_frame_map(
                                frame_map_path,
                                t0_sample_number=first_trigger_sample,
                                expected_total_frames=int(alignment["expected_total_frames"]),
                                usable_video_frame_start=int(alignment["usable_video_frame_start"]),
                                effective_fps=float(alignment["effective_fps"]),
                                sample_rate_hz=self.config.daq.sample_rate_hz,
                            )
                            self._write_alignment(alignment_path, alignment)
                            rel_seconds = 0.0
                            sample_offset = 0
                            window_remaining = self.config.window_minutes * 60.0
                            frame_index_from_t0 = 1
                            video_frame_index_estimated = int(alignment["video_t0_frame_estimated"])
                            with self._lock:
                                self._status.state = "recording"
                                self._status.first_trigger_at = now.isoformat(timespec="milliseconds")
                                self._status.t0_locked = True
                                self._status.expected_total_frames = int(alignment["expected_total_frames"])
                                self._status.video_t0_frame_estimated = int(alignment["video_t0_frame_estimated"])
                                self._status.usable_video_frame_start = int(alignment["usable_video_frame_start"])
                                self._status.usable_video_frame_end = int(alignment["usable_video_frame_end"])
                                self._status.preroll_seconds = float(alignment["preroll_seconds"])
                                self._status.window_remaining_seconds = window_remaining
                        else:
                            assert alignment is not None
                            sample_offset = detection.sample_number - first_trigger_sample
                            rel_seconds = (
                                sample_offset
                            ) / self.config.daq.sample_rate_hz
                            frame_index_from_t0 = 1 + round(rel_seconds * float(alignment["effective_fps"]))
                            video_frame_index_estimated = (
                                int(alignment["usable_video_frame_start"]) + frame_index_from_t0 - 1
                            )

                        assert target_end_sample is not None
                        window_remaining = (
                            target_end_sample - detection.sample_number
                        ) / self.config.daq.sample_rate_hz
                        if detection.sample_number >= target_end_sample:
                            frame_index_from_t0 = -1
                            video_frame_index_estimated = -1

                        with self._lock:
                            self._status.trigger_count += 1
                            self._status.elapsed_seconds = rel_seconds
                            self._status.window_remaining_seconds = window_remaining
                            trigger_index = self._status.trigger_count

                        row = {
                            "trigger_index": trigger_index,
                            "absolute_time": now.isoformat(timespec="milliseconds"),
                            "relative_time_seconds": f"{rel_seconds:.6f}",
                            "sample_number": detection.sample_number,
                            "frame_index": frame_index_from_t0,
                            "window_remaining": f"{window_remaining:.3f}",
                            "frame_mapping_mode": "estimated_fps",
                            "sample_offset_from_t0": sample_offset,
                            "frame_index_from_t0": frame_index_from_t0,
                            "video_frame_index_estimated": video_frame_index_estimated,
                            "timebase": "daq_sample_clock",
                        }
                        writer.writerow(row)
                        csv_file.flush()
                        db.execute(
                            """
                            insert into triggers values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                trigger_index,
                                row["absolute_time"],
                                rel_seconds,
                                detection.sample_number,
                                frame_index_from_t0,
                                window_remaining,
                                row["frame_mapping_mode"],
                                sample_offset,
                                frame_index_from_t0,
                                video_frame_index_estimated,
                                row["timebase"],
                            ),
                        )
                        db.commit()
                        self._append_jsonl(events_path, {"type": "trigger", "payload": row})
                        self.event_bus.publish("trigger", row)
                        self.event_bus.publish("status", self.status_dict())

                    if first_trigger_sample is not None and target_end_sample is not None:
                        self._update_recording_progress(first_trigger_sample, target_end_sample, global_sample)
                        self.event_bus.publish("status", self.status_dict())

                    if target_end_sample is not None and global_sample >= target_end_sample:
                        stop_overshoot_samples = max(0, global_sample - target_end_sample)
                        if alignment is not None:
                            alignment["stop_overshoot_samples"] = stop_overshoot_samples
                            alignment["stop_overshoot_seconds"] = stop_overshoot_samples / self.config.daq.sample_rate_hz
                            alignment["post_window_record_seconds"] = max(
                                0.0,
                                float(self.config.post_window_record_seconds),
                            )
                            alignment["finished_at_log_time"] = datetime.now().isoformat(timespec="milliseconds")
                        with self._lock:
                            self._status.stop_overshoot_samples = stop_overshoot_samples
                            self._status.video_trim_status = "post_recording"
                            self._finalize_trigger_capture_locked("finalizing")
                        self.event_bus.publish("status", self.status_dict())
                        if alignment is not None:
                            self._stop_camera_after_post_window_buffer()
                            with self._lock:
                                self._status.video_trim_status = "trimming"
                            self.event_bus.publish("status", self.status_dict())
                            self._finalize_aligned_video(alignment_path, alignment)
                            self._write_alignment(alignment_path, alignment)
                            with self._lock:
                                self._status.state = "finished"
                                self._worker = None
                            self.event_bus.publish("status", self.status_dict())
                        return
        except Exception as exc:  # noqa: BLE001
            self._logger.error("Acquisition loop failed: %s", exc)
            self._logger.debug("%s", traceback.format_exc())
            try:
                try:
                    self.daq.stop_sampling()
                except Exception as stop_exc:  # noqa: BLE001
                    self._logger.warning("DAQ stop after acquisition error failed: %s", stop_exc)
                try:
                    self._stop_all_cameras()
                except Exception as stop_exc:  # noqa: BLE001
                    self._logger.warning("Camera stop after acquisition error failed: %s", stop_exc)
            finally:
                self._set_error(str(exc))
            if (
                isinstance(exc, DaqError)
                and not self._stop_event.is_set()
                and not self._preview_stop_event.is_set()
            ):
                self._attempt_daq_recovery()

    def _publish_waveform(self, samples: List[float], global_sample: int) -> None:
        if not samples:
            return
        payload = {
            "sample_number": global_sample,
            "min": min(samples),
            "max": max(samples),
            "last": samples[-1],
            "points": samples[:: max(1, len(samples) // 80)],
        }
        self.event_bus.publish("waveform", payload)

    def _update_recording_progress(
        self,
        first_trigger_sample: int,
        target_end_sample: int,
        global_sample: int,
    ) -> None:
        current_sample = min(global_sample, target_end_sample)
        elapsed_seconds = max(
            0.0,
            (current_sample - first_trigger_sample) / self.config.daq.sample_rate_hz,
        )
        remaining_seconds = max(
            0.0,
            (target_end_sample - current_sample) / self.config.daq.sample_rate_hz,
        )
        with self._lock:
            self._status.elapsed_seconds = elapsed_seconds
            self._status.window_remaining_seconds = remaining_seconds
            self._status.t0_locked = True

    def _finalize_aligned_video(self, alignment_path: Path, alignment: Dict[str, Any]) -> None:
        source_text = self.status().video_file
        if not source_text:
            trim_result = {
                "status": "skipped",
                "reason": "source video path is missing",
            }
        else:
            source_video = Path(source_text)
            alignment["files"]["source_video"] = source_video.name
            output_video = source_video.with_name(f"{source_video.stem}_aligned{source_video.suffix}")
            trim_result = self._trim_video_from_t0(
                source_video=source_video,
                output_video=output_video,
                start_seconds=max(0.0, float(alignment["preroll_seconds"])),
                duration_seconds=float(alignment["window_seconds"]),
            )

        alignment["video_trim"] = trim_result
        if trim_result.get("status") == "ok":
            alignment["files"]["aligned_video"] = Path(str(trim_result["output_file"])).name
            with self._lock:
                self._status.aligned_video_file = str(trim_result["output_file"])
                self._status.video_trim_status = "ok"
        else:
            with self._lock:
                self._status.video_trim_status = str(trim_result.get("status", "failed"))
        self._append_jsonl(
            alignment_path.with_name("events.jsonl"),
            {"type": "video_trim", "payload": trim_result},
        )
        alignment["video_validation"] = self._validate_aligned_video(alignment, trim_result)
        frame_extract = self._extract_alignment_check_frames(alignment_path, alignment, trim_result)
        alignment["frame_extract"] = frame_extract
        if frame_extract.get("status") in {"ok", "warning"}:
            alignment["files"]["aligned_first_frame"] = Path(str(frame_extract["first_frame_file"])).name
            alignment["files"]["aligned_last_frame"] = Path(str(frame_extract["last_frame_file"])).name
        self._append_jsonl(
            alignment_path.with_name("events.jsonl"),
            {"type": "frame_extract", "payload": frame_extract},
        )
        if self.camera2 is not None and self.status().video_file2:
            camera2_result = self._finalize_secondary_aligned_video(alignment_path, alignment)
            alignment["camera2_video_trim"] = camera2_result.get("video_trim")
            alignment["camera2_video_validation"] = camera2_result.get("video_validation")
            alignment["camera2_frame_extract"] = camera2_result.get("frame_extract")
            self._append_jsonl(
                alignment_path.with_name("events.jsonl"),
                {"type": "camera2_video_finalize", "payload": camera2_result},
            )

    def _finalize_secondary_aligned_video(
        self,
        alignment_path: Path,
        alignment: Dict[str, Any],
    ) -> Dict[str, Any]:
        source_text = self.status().video_file2
        camera2_alignment = alignment.get("cameras", {}).get("camera2")
        if not source_text or not camera2_alignment:
            return {
                "video_trim": {
                    "status": "skipped",
                    "reason": "camera2 source video or alignment metadata is missing",
                }
            }
        source_video = Path(source_text)
        output_video = source_video.with_name(f"{source_video.stem}_aligned{source_video.suffix}")
        trim_result = self._trim_video_from_t0(
            source_video=source_video,
            output_video=output_video,
            start_seconds=max(0.0, float(camera2_alignment["preroll_seconds"])),
            duration_seconds=float(alignment["window_seconds"]),
        )
        if trim_result.get("status") == "ok":
            alignment["files"]["source_video_camera2"] = source_video.name
            alignment["files"]["aligned_video_camera2"] = Path(str(trim_result["output_file"])).name
            with self._lock:
                self._status.aligned_video_file2 = str(trim_result["output_file"])

        camera2_validation_alignment = {
            **alignment,
            "effective_fps": camera2_alignment["effective_fps"],
            "expected_total_frames": camera2_alignment["expected_total_frames"],
            "preroll_seconds": camera2_alignment["preroll_seconds"],
        }
        validation = self._validate_aligned_video(camera2_validation_alignment, trim_result)
        frame_extract = self._extract_alignment_check_frames(
            alignment_path,
            camera2_validation_alignment,
            trim_result,
            source_video_override=source_video,
            preroll_seconds_override=float(camera2_alignment["preroll_seconds"]),
            output_prefix="camera2_aligned",
        )
        if frame_extract.get("status") in {"ok", "warning"}:
            alignment["files"]["camera2_aligned_first_frame"] = Path(str(frame_extract["first_frame_file"])).name
            alignment["files"]["camera2_aligned_last_frame"] = Path(str(frame_extract["last_frame_file"])).name
        return {
            "video_trim": trim_result,
            "video_validation": validation,
            "frame_extract": frame_extract,
        }

    def _validate_aligned_video(self, alignment: Dict[str, Any], trim_result: Dict[str, Any]) -> Dict[str, Any]:
        ffprobe = self._resolve_ffprobe_executable()
        if trim_result.get("status") != "ok":
            return {
                "status": "not_checked",
                "warning": "Aligned video was not created.",
            }
        if not ffprobe:
            return {
                "status": "not_checked",
                "warning": "Video frame count validation requires ffprobe.",
            }
        video_file = Path(str(trim_result["output_file"]))
        command = [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=nb_read_frames,nb_frames,r_frame_rate,avg_frame_rate,duration",
            "-of",
            "json",
            str(video_file),
        ]
        try:
            completed = self._run_tracked(command, timeout=120)
            data = json.loads(completed.stdout)
            stream = data["streams"][0]
            actual_frames = int(stream.get("nb_read_frames") or stream.get("nb_frames") or 0)
            actual_duration = float(stream.get("duration") or 0.0)
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "failed",
                "warning": f"ffprobe validation failed: {exc}",
                "command": command,
            }
        expected_frames = int(alignment["expected_total_frames"])
        expected_duration = float(alignment["window_seconds"])
        frame_delta = actual_frames - expected_frames
        duration_delta = actual_duration - expected_duration
        status = "ok" if frame_delta == 0 else "warning"
        result: Dict[str, Any] = {
            "status": status,
            "expected_frames": expected_frames,
            "actual_frames": actual_frames,
            "frame_delta": frame_delta,
            "expected_duration_seconds": expected_duration,
            "actual_duration_seconds": actual_duration,
            "duration_delta_seconds": duration_delta,
            "r_frame_rate": stream.get("r_frame_rate"),
            "avg_frame_rate": stream.get("avg_frame_rate"),
            "command": command,
        }
        if status != "ok":
            result["warning"] = "Aligned video frame count differs from theoretical frame count."
        return result

    def _trim_video_from_t0(
        self,
        *,
        source_video: Path,
        output_video: Path,
        start_seconds: float,
        duration_seconds: float,
    ) -> Dict[str, Any]:
        if not self.config.video_trim_enabled:
            return {"status": "disabled", "reason": "MRC_VIDEO_TRIM_ENABLED is false"}
        if not source_video.exists() or source_video.stat().st_size == 0:
            return {
                "status": "skipped",
                "reason": "source video does not exist or is empty",
                "source_file": str(source_video),
            }

        ffmpeg = self._resolve_ffmpeg_executable()
        if not ffmpeg:
            return {
                "status": "skipped",
                "reason": "ffmpeg was not found; install ffmpeg or set MRC_FFMPEG",
                "source_file": str(source_video),
                "planned_output_file": str(output_video),
                "start_seconds": start_seconds,
                "duration_seconds": duration_seconds,
            }

        mode = self.config.video_trim_mode.lower()
        commands: List[tuple[str, List[str]]] = []
        if mode in {"copy", "stream_copy"}:
            commands.append((
                "copy",
                [
                    ffmpeg,
                    "-y",
                    "-ss",
                    f"{start_seconds:.6f}",
                    "-i",
                    str(source_video),
                    "-t",
                    f"{duration_seconds:.6f}",
                    "-c",
                    "copy",
                    str(output_video),
                ],
            ))
        else:
            commands.append((
                "reencode",
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(source_video),
                    "-ss",
                    f"{start_seconds:.6f}",
                    "-t",
                    f"{duration_seconds:.6f}",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "18",
                    "-c:a",
                    "copy",
                    str(output_video),
                ],
            ))
            commands.append((
                "copy_fallback",
                [
                    ffmpeg,
                    "-y",
                    "-ss",
                    f"{start_seconds:.6f}",
                    "-i",
                    str(source_video),
                    "-t",
                    f"{duration_seconds:.6f}",
                    "-c",
                    "copy",
                    str(output_video),
                ],
            ))

        errors: List[Dict[str, Any]] = []
        for label, command in commands:
            try:
                completed = self._run_tracked(command, timeout=900)
            except Exception as exc:  # noqa: BLE001
                errors.append({"mode": label, "error": str(exc)})
                continue

            if completed.returncode == 0 and output_video.exists() and output_video.stat().st_size > 0:
                return {
                    "status": "ok",
                    "mode": label,
                    "source_file": str(source_video),
                    "output_file": str(output_video),
                    "start_seconds": start_seconds,
                    "duration_seconds": duration_seconds,
                    "command": command,
                }
            errors.append(
                {
                    "mode": label,
                    "returncode": completed.returncode,
                    "stderr_tail": completed.stderr[-2000:],
                }
            )

        return {
            "status": "failed",
            "source_file": str(source_video),
            "planned_output_file": str(output_video),
            "start_seconds": start_seconds,
            "duration_seconds": duration_seconds,
            "errors": errors,
        }

    def _extract_alignment_check_frames(
        self,
        alignment_path: Path,
        alignment: Dict[str, Any],
        trim_result: Dict[str, Any],
        source_video_override: Optional[Path] = None,
        preroll_seconds_override: Optional[float] = None,
        output_prefix: str = "aligned",
    ) -> Dict[str, Any]:
        ffmpeg = self._resolve_ffmpeg_executable()
        if not ffmpeg:
            return {"status": "skipped", "reason": "ffmpeg was not found; cannot extract check frames"}

        output_dir = alignment_path.parent
        first_frame = output_dir / f"{output_prefix}_first_frame.jpg"
        last_frame = output_dir / f"{output_prefix}_last_frame.jpg"
        fps = max(1.0, float(alignment["effective_fps"]))
        frame_interval_seconds = 1.0 / fps
        window_seconds = float(alignment["window_seconds"])

        if trim_result.get("status") == "ok":
            video_source = Path(str(trim_result["output_file"]))
            first_seconds = 0.0
            last_seconds = max(0.0, window_seconds - frame_interval_seconds)
            timing_source = "aligned_video"
        else:
            source_text = str(source_video_override) if source_video_override else self.status().video_file
            if not source_text:
                return {"status": "skipped", "reason": "source video path is missing"}
            video_source = Path(source_text)
            first_seconds = max(
                0.0,
                float(preroll_seconds_override if preroll_seconds_override is not None else alignment["preroll_seconds"]),
            )
            last_seconds = max(first_seconds, first_seconds + window_seconds - frame_interval_seconds)
            timing_source = "source_video_estimated_t0"

        if not video_source.exists() or video_source.stat().st_size == 0:
            return {
                "status": "skipped",
                "reason": "video source does not exist or is empty",
                "video_source": str(video_source),
            }

        first_result = self._extract_video_frame(
            ffmpeg=ffmpeg,
            video_source=video_source,
            output_file=first_frame,
            timestamp_seconds=first_seconds,
        )
        last_result = self._extract_video_frame(
            ffmpeg=ffmpeg,
            video_source=video_source,
            output_file=last_frame,
            timestamp_seconds=last_seconds,
        )
        if first_result["status"] == "ok" and last_result["status"] == "ok":
            return {
                "status": "ok",
                "timing_source": timing_source,
                "video_source": str(video_source),
                "first_frame_file": str(first_frame),
                "last_frame_file": str(last_frame),
                "first_timestamp_seconds": first_seconds,
                "last_timestamp_seconds": last_seconds,
            }
        if first_result["status"] == "ok" and last_result["status"] != "ok":
            fallback_last_result = self._extract_video_tail_frame(
                ffmpeg=ffmpeg,
                video_source=video_source,
                output_file=last_frame,
            )
            if fallback_last_result["status"] == "ok":
                return {
                    "status": "warning",
                    "warning": "Theoretical last-frame extraction failed; extracted the actual video tail frame instead.",
                    "timing_source": timing_source,
                    "video_source": str(video_source),
                    "first_frame_file": str(first_frame),
                    "last_frame_file": str(last_frame),
                    "first_timestamp_seconds": first_seconds,
                    "last_timestamp_seconds": last_seconds,
                    "last_frame_fallback": fallback_last_result,
                }
        return {
            "status": "failed",
            "timing_source": timing_source,
            "video_source": str(video_source),
            "first_frame": first_result,
            "last_frame": last_result,
        }

    def _extract_video_frame(
        self,
        *,
        ffmpeg: str,
        video_source: Path,
        output_file: Path,
        timestamp_seconds: float,
    ) -> Dict[str, Any]:
        command = [
            ffmpeg,
            "-y",
            "-ss",
            f"{timestamp_seconds:.6f}",
            "-i",
            str(video_source),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_file),
        ]
        try:
            completed = self._run_tracked(command, timeout=120)
        except Exception as exc:  # noqa: BLE001
            return {"status": "failed", "error": str(exc), "command": command}
        if completed.returncode == 0 and output_file.exists() and output_file.stat().st_size > 0:
            return {
                "status": "ok",
                "output_file": str(output_file),
                "timestamp_seconds": timestamp_seconds,
                "command": command,
            }
        return {
            "status": "failed",
            "returncode": completed.returncode,
            "stderr_tail": completed.stderr[-2000:],
            "command": command,
        }

    def _extract_video_tail_frame(
        self,
        *,
        ffmpeg: str,
        video_source: Path,
        output_file: Path,
    ) -> Dict[str, Any]:
        command = [
            ffmpeg,
            "-y",
            "-sseof",
            "-0.050",
            "-i",
            str(video_source),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-update",
            "1",
            str(output_file),
        ]
        try:
            completed = self._run_tracked(command, timeout=120)
        except Exception as exc:  # noqa: BLE001
            return {"status": "failed", "error": str(exc), "command": command}
        if completed.returncode == 0 and output_file.exists() and output_file.stat().st_size > 0:
            return {
                "status": "ok",
                "output_file": str(output_file),
                "command": command,
            }
        return {
            "status": "failed",
            "returncode": completed.returncode,
            "stderr_tail": completed.stderr[-2000:],
            "command": command,
        }

    def _resolve_ffmpeg_executable(self) -> Optional[str]:
        if self.config.ffmpeg_path:
            return self.config.ffmpeg_path
        bundled = self.repo_root / "vendor" / "ffmpeg" / "windows" / "bin" / "ffmpeg.exe"
        if bundled.exists():
            return str(bundled)
        return shutil.which("ffmpeg")

    def _resolve_ffprobe_executable(self) -> Optional[str]:
        if self.config.ffmpeg_path:
            ffmpeg_path = Path(self.config.ffmpeg_path)
            ffprobe_path = ffmpeg_path.with_name("ffprobe.exe" if ffmpeg_path.suffix.lower() == ".exe" else "ffprobe")
            if ffprobe_path.exists():
                return str(ffprobe_path)
        bundled = self.repo_root / "vendor" / "ffmpeg" / "windows" / "bin" / "ffprobe.exe"
        if bundled.exists():
            return str(bundled)
        return shutil.which("ffprobe")

    def _build_alignment_metadata(
        self,
        sync_context: SyncStartContext,
        t0_sample_number: int,
        output_dir: Path,
    ) -> Dict[str, Any]:
        sample_rate_hz = self.config.daq.sample_rate_hz
        window_seconds = self.config.window_minutes * 60.0
        target_window_samples = int(round(window_seconds * sample_rate_hz))
        target_end_sample = t0_sample_number + target_window_samples
        effective_fps = float(self.camera.status().fps or self.config.camera.fps)
        expected_total_frames = int(round(window_seconds * effective_fps))
        t0_monotonic_ns = sync_context.daq_sample0_monotonic_ns + int(
            round((t0_sample_number / sample_rate_hz) * 1_000_000_000)
        )
        preroll_seconds = (
            t0_monotonic_ns - sync_context.camera_recording_started_monotonic_ns
        ) / 1_000_000_000
        video_t0_frame_estimated = 1 + round(preroll_seconds * effective_fps)
        usable_video_frame_start = video_t0_frame_estimated
        usable_video_frame_end = usable_video_frame_start + expected_total_frames - 1
        uncertainty_seconds = (
            sync_context.camera_recording_started_monotonic_ns
            - sync_context.camera_start_call_enter_monotonic_ns
        ) / 1_000_000_000
        camera1_alignment = {
            "label": "camera1",
            "device_index": self.config.camera.device_index,
            "video_source_index": self.config.camera.video_source_index,
            "effective_fps": effective_fps,
            "expected_total_frames": expected_total_frames,
            "camera_recording_started_monotonic_ns": sync_context.camera_recording_started_monotonic_ns,
            "camera_start_call_enter_monotonic_ns": sync_context.camera_start_call_enter_monotonic_ns,
            "camera_start_uncertainty_seconds": uncertainty_seconds,
            "preroll_seconds": preroll_seconds,
            "video_t0_frame_estimated": video_t0_frame_estimated,
            "usable_video_frame_start": usable_video_frame_start,
            "usable_video_frame_end": usable_video_frame_end,
        }
        cameras = {"camera1": camera1_alignment}
        if (
            self.camera2 is not None
            and sync_context.camera2_recording_started_monotonic_ns is not None
            and sync_context.camera2_start_call_enter_monotonic_ns is not None
        ):
            effective_fps2 = float(self.camera2.status().fps or self.config.camera2.fps)
            expected_total_frames2 = int(round(window_seconds * effective_fps2))
            preroll_seconds2 = (
                t0_monotonic_ns - sync_context.camera2_recording_started_monotonic_ns
            ) / 1_000_000_000
            video_t0_frame_estimated2 = 1 + round(preroll_seconds2 * effective_fps2)
            usable_video_frame_start2 = video_t0_frame_estimated2
            usable_video_frame_end2 = usable_video_frame_start2 + expected_total_frames2 - 1
            uncertainty_seconds2 = (
                sync_context.camera2_recording_started_monotonic_ns
                - sync_context.camera2_start_call_enter_monotonic_ns
            ) / 1_000_000_000
            cameras["camera2"] = {
                "label": "camera2",
                "device_index": self.config.camera2.device_index,
                "video_source_index": self.config.camera2.video_source_index,
                "effective_fps": effective_fps2,
                "expected_total_frames": expected_total_frames2,
                "camera_recording_started_monotonic_ns": sync_context.camera2_recording_started_monotonic_ns,
                "camera_start_call_enter_monotonic_ns": sync_context.camera2_start_call_enter_monotonic_ns,
                "camera_start_uncertainty_seconds": uncertainty_seconds2,
                "preroll_seconds": preroll_seconds2,
                "video_t0_frame_estimated": video_t0_frame_estimated2,
                "usable_video_frame_start": usable_video_frame_start2,
                "usable_video_frame_end": usable_video_frame_end2,
            }

        files = {
            "alignment": "alignment.json",
            "frame_map": "frame_map.csv",
            "triggers": "triggers.csv",
            "trigger_db": "triggers.sqlite3",
            "source_video": "mrc_recording.mp4" if self.config.camera.capture_format == 2 else "mrc_recording.avi",
        }
        if "camera2" in cameras:
            files["source_video_camera2"] = (
                "mrc_recording_camera2.mp4"
                if self.config.camera2.capture_format == 2
                else "mrc_recording_camera2.avi"
            )

        return {
            "schema_version": 1,
            "sync_mode": "preroll_first_trigger_t0",
            "timebase": "daq_sample_clock",
            "confidence": "software_estimated_fps; not hardware exposure sync",
            "output_dir": str(output_dir),
            "sample_rate_hz": sample_rate_hz,
            "window_seconds": window_seconds,
            "target_window_samples": target_window_samples,
            "target_end_sample": target_end_sample,
            "effective_fps": effective_fps,
            "expected_total_frames": expected_total_frames,
            "camera_recording_started_monotonic_ns": sync_context.camera_recording_started_monotonic_ns,
            "camera_start_call_enter_monotonic_ns": sync_context.camera_start_call_enter_monotonic_ns,
            "camera_start_uncertainty_seconds": uncertainty_seconds,
            "daq_sample0_monotonic_ns": sync_context.daq_sample0_monotonic_ns,
            "t0_sample_number": t0_sample_number,
            "t0_monotonic_ns": t0_monotonic_ns,
            "preroll_seconds": preroll_seconds,
            "video_t0_frame_estimated": video_t0_frame_estimated,
            "usable_video_frame_start": usable_video_frame_start,
            "usable_video_frame_end": usable_video_frame_end,
            "cameras": cameras,
            "stop_overshoot_samples": None,
            "stop_overshoot_seconds": None,
            "video_validation": {
                "status": "not_checked",
                "warning": "Video frame count validation requires an external decoder such as ffprobe.",
            },
            "files": files,
        }

    @staticmethod
    def _write_alignment(path: Path, alignment: Dict[str, Any]) -> None:
        path.write_text(json.dumps(alignment, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _write_frame_map(
        path: Path,
        *,
        t0_sample_number: int,
        expected_total_frames: int,
        usable_video_frame_start: int,
        effective_fps: float,
        sample_rate_hz: int,
    ) -> None:
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=[
                    "relative_frame_index",
                    "video_frame_index_estimated",
                    "relative_time_seconds",
                    "estimated_sample_number",
                ],
            )
            writer.writeheader()
            for relative_frame_index in range(1, expected_total_frames + 1):
                relative_time_seconds = (relative_frame_index - 1) / effective_fps
                writer.writerow(
                    {
                        "relative_frame_index": relative_frame_index,
                        "video_frame_index_estimated": usable_video_frame_start + relative_frame_index - 1,
                        "relative_time_seconds": f"{relative_time_seconds:.9f}",
                        "estimated_sample_number": t0_sample_number
                        + round(relative_time_seconds * sample_rate_hz),
                    }
                )

    @staticmethod
    def _append_jsonl(path: Path, event: Dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

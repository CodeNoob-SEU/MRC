from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
import csv
import json
import logging
import shutil
import sqlite3
import subprocess
import threading
import time
import traceback
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .config import AppConfig
from .events import EventBus
from .hardware.camera import BaseCamera, CameraStatus, build_camera
from .hardware.daq import BaseDaq, DaqStatus, TriggerDetector, build_daq


@dataclass
class ExperimentStatus:
    state: str = "idle"
    recording_mode: str = "trigger"
    session_id: Optional[str] = None
    output_dir: Optional[str] = None
    video_file: Optional[str] = None
    aligned_video_file: Optional[str] = None
    video_trim_status: Optional[str] = None
    trigger_count: int = 0
    started_at: Optional[str] = None
    first_trigger_at: Optional[str] = None
    elapsed_seconds: float = 0.0
    window_remaining_seconds: Optional[float] = None
    last_error: Optional[str] = None
    camera: Optional[Dict[str, Any]] = None
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


class ExperimentCoordinator:
    def __init__(self, config: AppConfig, repo_root: Path, event_bus: EventBus) -> None:
        self.config = config
        self.repo_root = repo_root
        self.event_bus = event_bus
        self.camera: BaseCamera = build_camera(config.hardware_mode, config.camera, repo_root)
        self.daq: BaseDaq = build_daq(config.hardware_mode, config.daq, repo_root)
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._preview_stop_event = threading.Event()
        self._preview_worker: Optional[threading.Thread] = None
        self._status = ExperimentStatus(
            camera=asdict(self.camera.status()),
            daq=asdict(self.daq.status()),
        )
        self._logger = logging.getLogger("mrc_backend.experiment")

    def initialize(self) -> ExperimentStatus:
        with self._lock:
            camera_status = self.camera.initialize()
            daq_status = self.daq.initialize()
            self._status.camera = asdict(camera_status)
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
                "daq": asdict(self.daq.status()),
            }

    def diagnostics(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "hardware_mode": self.config.hardware_mode,
            "camera": {
                "ok": False,
                "status": asdict(self.camera.status()),
                "devices": [],
                "error": None,
            },
            "daq": {"ok": False, "status": asdict(self.daq.status()), "error": None},
        }
        try:
            enumerate_devices = getattr(self.camera, "enumerate_devices")
            result["camera"]["devices"] = enumerate_devices()
        except Exception as exc:  # noqa: BLE001
            result["camera"]["devices_error"] = str(exc)

        try:
            result["camera"]["status"] = asdict(self.camera.initialize())
            result["camera"]["ok"] = True
        except Exception as exc:  # noqa: BLE001
            result["camera"]["status"] = asdict(self.camera.status())
            result["camera"]["error"] = str(exc)

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
            if self._status.state in {"armed", "recording", "manual_recording"}:
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

            camera_start_call_enter_monotonic_ns = time.monotonic_ns()
            camera_status = self.camera.start_recording(video_file)
            active_video_file = Path(camera_status.active_file or str(video_file))
            camera_recording_started_monotonic_ns = time.monotonic_ns()
            daq_status = self.daq.start_sampling()
            daq_sample0_monotonic_ns = daq_status.sample0_monotonic_ns or time.monotonic_ns()
            sync_context = SyncStartContext(
                camera_start_call_enter_monotonic_ns=camera_start_call_enter_monotonic_ns,
                camera_recording_started_monotonic_ns=camera_recording_started_monotonic_ns,
                daq_sample0_monotonic_ns=daq_sample0_monotonic_ns,
            )
            self._stop_event.clear()
            self._status = ExperimentStatus(
                state="armed",
                recording_mode="trigger",
                session_id=session_id,
                output_dir=str(output_dir),
                video_file=str(active_video_file),
                trigger_count=0,
                started_at=datetime.now().isoformat(timespec="milliseconds"),
                camera=asdict(camera_status),
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
            if self._status.state in {"armed", "recording", "manual_recording"}:
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

            camera_status = self.camera.start_recording(video_file)
            active_video_file = Path(camera_status.active_file or str(video_file))
            self._status = ExperimentStatus(
                state="manual_recording",
                recording_mode="manual",
                session_id=session_id,
                output_dir=str(output_dir),
                video_file=str(active_video_file),
                started_at=datetime.now().isoformat(timespec="milliseconds"),
                camera=asdict(camera_status),
                daq=asdict(self.daq.status()),
            )
            self._append_jsonl(
                events_path,
                {
                    "type": "manual_recording_started",
                    "payload": {
                        "video_file": str(active_video_file),
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
                self.camera.stop_recording()
                self._status.state = "manual_stopped"
                self._status.camera = asdict(self.camera.status())
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
        self.daq.close()
        self.camera.close()

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
        interval_seconds = 1.0 / max(1.0, min(30.0, float(self.config.camera.preview_fps)))
        last_error_message = ""
        last_error_at = 0.0
        while not self._preview_stop_event.is_set():
            started_at = time.monotonic()
            try:
                frame = self.camera.preview_frame_data_url()
                if frame:
                    self.event_bus.publish(
                        "preview",
                        {
                            "src": frame,
                            "mode": self.camera.status().mode,
                            "recording": self.camera.status().recording,
                        },
                    )
                    last_error_message = ""
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                now = time.monotonic()
                if message != last_error_message or now - last_error_at >= 1.0:
                    self.event_bus.publish("preview_error", {"message": message})
                    last_error_message = message
                    last_error_at = now
            elapsed_seconds = time.monotonic() - started_at
            self._preview_stop_event.wait(max(0.0, interval_seconds - elapsed_seconds))

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._status.state = "error"
            self._status.last_error = message
            self._status.camera = asdict(self.camera.status())
            self._status.daq = asdict(self.daq.status())
        self.event_bus.publish("error", {"message": message})
        self.event_bus.publish("status", self.status_dict())

    def _set_finished_locked(self, state: str = "finished") -> None:
        try:
            self.daq.stop_sampling()
        finally:
            self.camera.stop_recording()
        self._status.state = state
        self._status.camera = asdict(self.camera.status())
        self._status.daq = asdict(self.daq.status())
        self._worker = None

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
                            alignment["finished_at_log_time"] = datetime.now().isoformat(timespec="milliseconds")
                        with self._lock:
                            self._status.stop_overshoot_samples = stop_overshoot_samples
                            self._status.video_trim_status = "trimming"
                            self._set_finished_locked("finished")
                        self.event_bus.publish("status", self.status_dict())
                        if alignment is not None:
                            self._finalize_aligned_video(alignment_path, alignment)
                            self._write_alignment(alignment_path, alignment)
                            self.event_bus.publish("status", self.status_dict())
                        return
        except Exception as exc:  # noqa: BLE001
            self._logger.error("Acquisition loop failed: %s", exc)
            self._logger.debug("%s", traceback.format_exc())
            try:
                self.daq.stop_sampling()
                self.camera.stop_recording()
            finally:
                self._set_error(str(exc))

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
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=900,
                )
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

    def _resolve_ffmpeg_executable(self) -> Optional[str]:
        if self.config.ffmpeg_path:
            return self.config.ffmpeg_path
        bundled = self.repo_root / "vendor" / "ffmpeg" / "windows" / "bin" / "ffmpeg.exe"
        if bundled.exists():
            return str(bundled)
        return shutil.which("ffmpeg")

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
            "stop_overshoot_samples": None,
            "stop_overshoot_seconds": None,
            "video_validation": {
                "status": "not_checked",
                "warning": "Video frame count validation requires an external decoder such as ffprobe.",
            },
            "files": {
                "alignment": "alignment.json",
                "frame_map": "frame_map.csv",
                "triggers": "triggers.csv",
                "trigger_db": "triggers.sqlite3",
                "source_video": "mrc_recording.mp4" if self.config.camera.capture_format == 2 else "mrc_recording.avi",
            },
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

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
import csv
import json
import logging
import sqlite3
import threading
import traceback
from typing import Any
from uuid import uuid4

from .config import AppConfig
from .events import EventBus
from .hardware.camera import BaseCamera, CameraStatus, build_camera
from .hardware.daq import BaseDaq, DaqStatus, TriggerDetector, build_daq


@dataclass(slots=True)
class ExperimentStatus:
    state: str = "idle"
    session_id: str | None = None
    output_dir: str | None = None
    video_file: str | None = None
    trigger_count: int = 0
    started_at: str | None = None
    first_trigger_at: str | None = None
    elapsed_seconds: float = 0.0
    window_remaining_seconds: float | None = None
    last_error: str | None = None
    camera: dict[str, Any] | None = None
    daq: dict[str, Any] | None = None


class ExperimentCoordinator:
    def __init__(self, config: AppConfig, repo_root: Path, event_bus: EventBus) -> None:
        self.config = config
        self.repo_root = repo_root
        self.event_bus = event_bus
        self.camera: BaseCamera = build_camera(config.hardware_mode, config.camera, repo_root)
        self.daq: BaseDaq = build_daq(config.hardware_mode, config.daq, repo_root)
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._preview_stop_event = threading.Event()
        self._preview_worker: threading.Thread | None = None
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

    def devices(self) -> dict[str, Any]:
        with self._lock:
            return {
                "hardware_mode": self.config.hardware_mode,
                "camera": asdict(self.camera.status()),
                "daq": asdict(self.daq.status()),
            }

    def start_experiment(
        self,
        output_root: str | None = None,
        window_minutes: float | None = None,
        camera_fps: float | None = None,
        threshold_volts: float | None = None,
    ) -> ExperimentStatus:
        with self._lock:
            if self._status.state in {"armed", "recording"}:
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
            video_file = output_dir / "mrc_recording.mp4"

            self.camera.start_recording(video_file)
            self.daq.start_sampling()
            self._stop_event.clear()
            self._status = ExperimentStatus(
                state="armed",
                session_id=session_id,
                output_dir=str(output_dir),
                video_file=str(video_file),
                trigger_count=0,
                started_at=datetime.now().isoformat(timespec="milliseconds"),
                camera=asdict(self.camera.status()),
                daq=asdict(self.daq.status()),
            )
            self._worker = threading.Thread(
                target=self._acquisition_loop,
                args=(output_dir,),
                name="mrc-acquisition",
                daemon=True,
            )
            self._worker.start()
        self.event_bus.publish("status", self.status_dict())
        return self.status()

    def stop_experiment(self) -> ExperimentStatus:
        worker: threading.Thread | None
        with self._lock:
            worker = self._worker
            self._stop_event.set()
        if worker is not None and worker.is_alive():
            worker.join(timeout=5.0)
        with self._lock:
            if self._status.state in {"armed", "recording"}:
                self._set_finished_locked("stopped")
        self.event_bus.publish("status", self.status_dict())
        return self.status()

    def status(self) -> ExperimentStatus:
        with self._lock:
            return replace(self._status)

    def status_dict(self) -> dict[str, Any]:
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
        while not self._preview_stop_event.is_set():
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
            except Exception as exc:  # noqa: BLE001
                self.event_bus.publish("preview_error", {"message": str(exc)})
            self._preview_stop_event.wait(0.5)

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

    def _acquisition_loop(self, output_dir: Path) -> None:
        trigger_csv = output_dir / "triggers.csv"
        db_path = output_dir / "triggers.sqlite3"
        events_path = output_dir / "events.jsonl"
        detector = TriggerDetector(
            threshold=self.config.daq.threshold_volts,
            debounce_seconds=self.config.daq.debounce_seconds,
            sample_rate_hz=self.config.daq.sample_rate_hz,
        )
        global_sample = 0
        first_trigger_sample: int | None = None
        end_sample: int | None = None

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
                        frame_mapping_mode text not null
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
                            end_sample = first_trigger_sample + int(
                                self.config.window_minutes * 60 * self.config.daq.sample_rate_hz
                            )
                            rel_seconds = 0.0
                            frame_index = 1
                            with self._lock:
                                self._status.state = "recording"
                                self._status.first_trigger_at = now.isoformat(timespec="milliseconds")
                        else:
                            rel_seconds = (
                                detection.sample_number - first_trigger_sample
                            ) / self.config.daq.sample_rate_hz
                            frame_index = 1 + round(rel_seconds * self.config.camera.fps)

                        assert end_sample is not None
                        window_remaining = (
                            end_sample - detection.sample_number
                        ) / self.config.daq.sample_rate_hz
                        if detection.sample_number > end_sample:
                            frame_index = -1

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
                            "frame_index": frame_index,
                            "window_remaining": f"{window_remaining:.3f}",
                            "frame_mapping_mode": "estimated_fps",
                        }
                        writer.writerow(row)
                        csv_file.flush()
                        db.execute(
                            """
                            insert into triggers values (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                trigger_index,
                                row["absolute_time"],
                                rel_seconds,
                                detection.sample_number,
                                frame_index,
                                window_remaining,
                                row["frame_mapping_mode"],
                            ),
                        )
                        db.commit()
                        self._append_jsonl(events_path, {"type": "trigger", "payload": row})
                        self.event_bus.publish("trigger", row)
                        self.event_bus.publish("status", self.status_dict())

                    if end_sample is not None and global_sample > end_sample:
                        with self._lock:
                            self._set_finished_locked("finished")
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

    def _publish_waveform(self, samples: list[float], global_sample: int) -> None:
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

    @staticmethod
    def _append_jsonl(path: Path, event: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

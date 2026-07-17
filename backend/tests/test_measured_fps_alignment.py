import csv
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from mrc_backend.config import AppConfig
from mrc_backend.events import EventBus
from mrc_backend.experiment import ExperimentCoordinator


def make_timing(nominal_fps: float, measured_fps: float) -> dict:
    return {
        "status": "ok",
        "nominal_fps": nominal_fps,
        "measured_fps": measured_fps,
        "video_time_ratio": measured_fps / nominal_fps,
        "wall_recording_seconds": 100.0,
        "video_duration_seconds": 100.0 * measured_fps / nominal_fps,
        "frame_count": int(round(100.0 * measured_fps)),
    }


def make_coordinator(config: AppConfig) -> ExperimentCoordinator:
    config.hardware_mode = "mock"
    return ExperimentCoordinator(config, Path.cwd(), EventBus())


class MeasuredFpsAlignmentTest(unittest.TestCase):
    def test_apply_measured_timing_recomputes_frame_fields(self) -> None:
        coordinator = make_coordinator(AppConfig())
        alignment = {
            "window_seconds": 480.0,
            "preroll_seconds": 5.0,
            "effective_fps": 30.0,
            "expected_total_frames": 14400,
            "video_t0_frame_estimated": 151,
            "usable_video_frame_start": 151,
            "usable_video_frame_end": 14550,
            "confidence": "software_estimated_fps",
            "cameras": {
                "camera1": {
                    "preroll_seconds": 5.0,
                    "effective_fps": 30.0,
                    "expected_total_frames": 14400,
                    "video_t0_frame_estimated": 151,
                    "usable_video_frame_start": 151,
                    "usable_video_frame_end": 14550,
                }
            },
        }
        timing = make_timing(nominal_fps=30.0, measured_fps=29.8)
        coordinator._apply_measured_timing_to_alignment(alignment, timing)

        self.assertEqual(alignment["effective_fps"], 29.8)
        self.assertEqual(alignment["nominal_fps"], 30.0)
        self.assertEqual(alignment["fps_source"], "measured_frames_vs_wall_clock")
        self.assertEqual(alignment["expected_total_frames"], round(480 * 29.8))
        self.assertEqual(alignment["video_t0_frame_estimated"], 1 + round(5.0 * 29.8))
        self.assertEqual(
            alignment["usable_video_frame_end"],
            alignment["usable_video_frame_start"] + alignment["expected_total_frames"] - 1,
        )
        self.assertAlmostEqual(alignment["video_window_seconds"], 480 * 29.8 / 30.0)
        self.assertAlmostEqual(alignment["video_preroll_seconds"], 5.0 * 29.8 / 30.0)
        # preroll stays in wall-clock seconds; only derived fields change
        self.assertEqual(alignment["preroll_seconds"], 5.0)
        self.assertEqual(alignment["cameras"]["camera1"]["effective_fps"], 29.8)

    def test_rewrite_trigger_frames_uses_measured_fps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            coordinator = make_coordinator(AppConfig())
            db_path = output_dir / "triggers.sqlite3"
            with closing(sqlite3.connect(db_path)) as db:
                db.execute(
                    """
                    create table triggers (
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
                # one trigger 10 s after t0, one beyond the window end
                db.execute(
                    "insert into triggers values (1, 't1', 10.0, 50000, 301, 470.0, "
                    "'estimated_fps', 50000, 301, 451, 'daq_sample_clock')"
                )
                db.execute(
                    "insert into triggers values (2, 't2', 480.1, 2400500, -1, 0.0, "
                    "'estimated_fps', 2400500, -1, -1, 'daq_sample_clock')"
                )
                db.commit()

            alignment = {
                "effective_fps": 29.8,
                "usable_video_frame_start": 150,
                "target_end_sample": 2400000,
            }
            coordinator._rewrite_trigger_frames(output_dir, alignment)

            expected_frame = 1 + round(10.0 * 29.8)  # 299
            with closing(sqlite3.connect(db_path)) as db:
                row1, row2 = db.execute(
                    "select frame_index_from_t0, video_frame_index_estimated, frame_mapping_mode "
                    "from triggers order by trigger_index"
                ).fetchall()
            self.assertEqual(row1, (expected_frame, 150 + expected_frame - 1, "measured_fps"))
            self.assertEqual(row2, (-1, -1, "measured_fps"))

            with (output_dir / "triggers.csv").open(newline="", encoding="utf-8") as file:
                csv_rows = list(csv.DictReader(file))
            self.assertEqual(len(csv_rows), 2)
            self.assertEqual(int(csv_rows[0]["frame_index_from_t0"]), expected_frame)
            self.assertEqual(csv_rows[0]["frame_mapping_mode"], "measured_fps")

    def test_mock_experiment_finalizes_with_measured_fps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = AppConfig()
            config.output_root = temp_dir
            config.video_trim_enabled = False
            config.window_minutes = 0.002
            config.camera.fps = 30
            config.daq.mock_trigger_interval_seconds = 0.05
            config.daq.batch_points = 50
            coordinator = make_coordinator(config)
            timing = make_timing(nominal_fps=30.0, measured_fps=29.0)
            coordinator._measure_video_timing = lambda **kwargs: dict(timing)  # type: ignore[method-assign]
            coordinator.initialize()
            status = coordinator.start_experiment()

            deadline = time.time() + 10
            while time.time() < deadline:
                status = coordinator.status()
                if status.state == "finished":
                    break
                time.sleep(0.02)
            coordinator.close()

            self.assertEqual(status.state, "finished")
            output_dir = Path(status.output_dir or "")
            alignment = json.loads((output_dir / "alignment.json").read_text(encoding="utf-8"))
            window_seconds = 0.002 * 60
            self.assertEqual(alignment["effective_fps"], 29.0)
            self.assertEqual(alignment["nominal_fps"], 30.0)
            self.assertEqual(alignment["expected_total_frames"], round(window_seconds * 29.0))
            self.assertAlmostEqual(alignment["video_window_seconds"], window_seconds * 29.0 / 30.0)
            self.assertEqual(alignment["video_timing"]["status"], "ok")
            self.assertEqual(status.expected_total_frames, alignment["expected_total_frames"])

            with (output_dir / "frame_map.csv").open(newline="", encoding="utf-8") as file:
                frame_rows = list(csv.DictReader(file))
            self.assertEqual(len(frame_rows), alignment["expected_total_frames"])

            with (output_dir / "triggers.csv").open(newline="", encoding="utf-8") as file:
                trigger_rows = list(csv.DictReader(file))
            self.assertGreaterEqual(len(trigger_rows), 1)
            self.assertEqual(trigger_rows[0]["frame_mapping_mode"], "measured_fps")


if __name__ == "__main__":
    unittest.main()

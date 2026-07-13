import csv
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from mrc_backend.config import AppConfig
from mrc_backend.events import EventBus
from mrc_backend.experiment import ExperimentCoordinator, SyncStartContext


class CoordinatorMockTest(unittest.TestCase):
    def test_camera2_config_inherits_camera1_connection_defaults(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "MRC_HARDWARE_MODE": "mock",
                "MRC_CAMERA_DEVICE_INDEX": "3",
                "MRC_CAMERA_WIDTH": "768",
                "MRC_CAMERA_HEIGHT": "576",
                "MRC_CAMERA_FPS": "25",
                "MRC_CAMERA_VIDEO_STANDARD": "32",
                "MRC_CAMERA_COLORSPACE": "2",
                "MRC_CAMERA_SAVE_AUDIO": "true",
                "MRC_CAMERA_CAPTURE_FORMAT": "1",
                "MRC_CAMERA_VIDEO_CODEC": "x264 Codec",
                "MRC_CAMERA_VIDEO_SOURCE_INDEX": "1",
                "MRC_CAMERA_PREVIEW_MODE": "2",
                "MRC_CAMERA_PREVIEW_FPS": "12",
                "MRC_CAMERA2_ENABLED": "1",
            },
            clear=True,
        ):
            env_config = AppConfig.from_env()

        self.assertTrue(env_config.camera2_enabled)
        self.assertEqual(env_config.camera2.device_index, env_config.camera.device_index + 1)
        self.assertEqual(env_config.camera2.fps, env_config.camera.fps)
        self.assertEqual(env_config.camera2.width, env_config.camera.width)
        self.assertEqual(env_config.camera2.height, env_config.camera.height)
        self.assertEqual(env_config.camera2.video_standard, env_config.camera.video_standard)
        self.assertEqual(env_config.camera2.colorspace, env_config.camera.colorspace)
        self.assertEqual(env_config.camera2.save_audio, env_config.camera.save_audio)
        self.assertEqual(env_config.camera2.capture_format, env_config.camera.capture_format)
        self.assertEqual(env_config.camera2.video_codec, env_config.camera.video_codec)
        self.assertEqual(env_config.camera2.video_source_index, env_config.camera.video_source_index)
        self.assertEqual(env_config.camera2.preview_mode, env_config.camera.preview_mode)
        self.assertEqual(env_config.camera2.preview_fps, env_config.camera.preview_fps)

    def test_mock_experiment_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = AppConfig()
            config.hardware_mode = "mock"
            config.output_root = temp_dir
            config.video_trim_enabled = False
            config.window_minutes = 0.001
            config.daq.mock_trigger_interval_seconds = 0.02
            config.daq.batch_points = 50
            coordinator = ExperimentCoordinator(config, Path.cwd(), EventBus())
            coordinator.initialize()
            status = coordinator.start_experiment()

            deadline = time.time() + 3
            while time.time() < deadline:
                status = coordinator.status()
                if status.state == "finished":
                    break
                time.sleep(0.02)

            self.assertEqual(status.state, "finished")
            self.assertGreaterEqual(status.trigger_count, 1)
            output_dir = Path(status.output_dir or "")
            self.assertTrue((output_dir / "triggers.csv").exists())
            self.assertTrue((output_dir / "triggers.sqlite3").exists())
            self.assertTrue((output_dir / "config_snapshot.json").exists())
            coordinator.close()

    def test_alignment_outputs_are_based_on_first_trigger_t0(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = AppConfig()
            config.hardware_mode = "mock"
            config.output_root = temp_dir
            config.video_trim_enabled = False
            config.window_minutes = 0.002
            config.camera.fps = 30
            config.daq.mock_trigger_interval_seconds = 0.05
            config.daq.batch_points = 50
            coordinator = ExperimentCoordinator(config, Path.cwd(), EventBus())
            coordinator.initialize()
            status = coordinator.start_experiment()

            deadline = time.time() + 3
            while time.time() < deadline:
                status = coordinator.status()
                if status.state == "finished":
                    break
                time.sleep(0.02)

            self.assertEqual(status.state, "finished")
            output_dir = Path(status.output_dir or "")
            alignment = json.loads((output_dir / "alignment.json").read_text(encoding="utf-8"))
            self.assertEqual(alignment["timebase"], "daq_sample_clock")
            self.assertEqual(alignment["t0_sample_number"], 250)
            self.assertGreater(alignment["video_t0_frame_estimated"], 1)
            self.assertEqual(alignment["expected_total_frames"], round(0.002 * 60 * 30))
            self.assertEqual(
                alignment["usable_video_frame_end"],
                alignment["usable_video_frame_start"] + alignment["expected_total_frames"] - 1,
            )
            self.assertIsNotNone(alignment["stop_overshoot_samples"])
            self.assertEqual(alignment["video_trim"]["status"], "disabled")
            self.assertEqual(status.window_remaining_seconds, 0.0)

            with (output_dir / "frame_map.csv").open(newline="", encoding="utf-8") as file:
                frame_rows = list(csv.DictReader(file))
            self.assertEqual(len(frame_rows), alignment["expected_total_frames"])
            self.assertEqual(int(frame_rows[0]["relative_frame_index"]), 1)
            self.assertEqual(
                int(frame_rows[0]["video_frame_index_estimated"]),
                alignment["usable_video_frame_start"],
            )

            with (output_dir / "triggers.csv").open(newline="", encoding="utf-8") as file:
                trigger_rows = list(csv.DictReader(file))
            self.assertGreaterEqual(len(trigger_rows), 2)
            self.assertEqual(int(trigger_rows[0]["sample_offset_from_t0"]), 0)
            self.assertEqual(int(trigger_rows[0]["frame_index_from_t0"]), 1)
            self.assertEqual(
                int(trigger_rows[0]["video_frame_index_estimated"]),
                alignment["video_t0_frame_estimated"],
            )
            second_sample_offset = int(trigger_rows[1]["sample_offset_from_t0"])
            expected_second_frame = 1 + round(second_sample_offset / config.daq.sample_rate_hz * config.camera.fps)
            self.assertEqual(int(trigger_rows[1]["frame_index_from_t0"]), expected_second_frame)
            self.assertEqual(trigger_rows[0]["timebase"], "daq_sample_clock")

            with closing(sqlite3.connect(output_dir / "triggers.sqlite3")) as db:
                db_row = db.execute(
                    "select sample_offset_from_t0, frame_index_from_t0, video_frame_index_estimated, timebase "
                    "from triggers order by trigger_index limit 1"
                ).fetchone()
            self.assertEqual(db_row, (0, 1, alignment["video_t0_frame_estimated"], "daq_sample_clock"))
            coordinator.close()

    def test_six_minute_window_expected_total_frames(self) -> None:
        config = AppConfig()
        config.hardware_mode = "mock"
        config.window_minutes = 6
        config.camera.fps = 30
        coordinator = ExperimentCoordinator(config, Path.cwd(), EventBus())
        alignment = coordinator._build_alignment_metadata(
            SyncStartContext(
                camera_start_call_enter_monotonic_ns=0,
                camera_recording_started_monotonic_ns=0,
                daq_sample0_monotonic_ns=0,
            ),
            t0_sample_number=0,
            output_dir=Path.cwd(),
        )
        self.assertEqual(alignment["expected_total_frames"], 10800)

    def test_dual_camera_mock_writes_second_camera_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = AppConfig()
            config.hardware_mode = "mock"
            config.camera2_enabled = True
            config.output_root = temp_dir
            config.video_trim_enabled = False
            config.window_minutes = 0.001
            config.camera.fps = 30
            config.camera2.fps = 30
            config.daq.mock_trigger_interval_seconds = 0.02
            config.daq.batch_points = 50
            coordinator = ExperimentCoordinator(config, Path.cwd(), EventBus())
            coordinator.initialize()
            status = coordinator.start_experiment()

            deadline = time.time() + 3
            while time.time() < deadline:
                status = coordinator.status()
                if status.state == "finished":
                    break
                time.sleep(0.02)

            self.assertEqual(status.state, "finished")
            self.assertIsNotNone(status.camera2)
            self.assertIsNotNone(status.video_file2)
            output_dir = Path(status.output_dir or "")
            self.assertTrue((output_dir / "mrc_recording_camera2.mp4").exists())
            alignment = json.loads((output_dir / "alignment.json").read_text(encoding="utf-8"))
            self.assertIn("camera2", alignment["cameras"])
            self.assertEqual(alignment["cameras"]["camera2"]["expected_total_frames"], alignment["expected_total_frames"])
            self.assertEqual(alignment["camera2_video_trim"]["status"], "disabled")
            self.assertEqual(alignment["files"]["source_video_camera2"], "mrc_recording_camera2.mp4")
            coordinator.close()

    def test_manual_recording_only_controls_camera(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = AppConfig()
            config.hardware_mode = "mock"
            config.output_root = temp_dir
            coordinator = ExperimentCoordinator(config, Path.cwd(), EventBus())
            coordinator.initialize()

            status = coordinator.start_manual_recording()
            self.assertEqual(status.state, "manual_recording")
            self.assertEqual(status.recording_mode, "manual")
            self.assertTrue(status.camera["recording"])
            output_dir = Path(status.output_dir or "")
            self.assertTrue((output_dir / "manual_recording.mp4").exists())
            self.assertFalse((output_dir / "triggers.csv").exists())
            self.assertFalse((output_dir / "alignment.json").exists())

            status = coordinator.stop_experiment()
            self.assertEqual(status.state, "manual_stopped")
            self.assertFalse(status.camera["recording"])
            coordinator.close()


if __name__ == "__main__":
    unittest.main()

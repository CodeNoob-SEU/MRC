"""Strict, timestamp-based trigger->frame alignment.

These tests exercise the path that replaces the global effective_fps
interpolation with a lookup against real per-frame capture timestamps
(frame_times.csv). They run off-Windows using synthetic timestamp tables.
"""

import csv
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from typing import List, Tuple

from mrc_backend.config import AppConfig
from mrc_backend.events import EventBus
from mrc_backend.experiment import ExperimentCoordinator


FPS = 30.0


def make_coordinator() -> ExperimentCoordinator:
    config = AppConfig()
    config.hardware_mode = "mock"
    return ExperimentCoordinator(config, Path.cwd(), EventBus())


def uniform_seconds(n: int, fps: float = FPS) -> List[float]:
    return [k / fps for k in range(n)]


def seconds_with_burst_drop(
    before: int, gap_seconds: float, after: int, fps: float = FPS
) -> List[float]:
    """`before` frames at fps, then a stall of `gap_seconds`, then `after` more."""
    seconds = [k / fps for k in range(before)]
    base = seconds[-1] + gap_seconds
    seconds.extend(base + j / fps for j in range(after))
    return seconds


def write_frame_times(path: Path, seconds: List[float]) -> None:
    # Matches the self-built pipeline's sidecar: index + real capture time.
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["video_frame_index", "capture_ns"])
        for index, value in enumerate(seconds):
            writer.writerow([index, int(value * 1_000_000_000)])


def make_triggers_db(db_path: Path, triggers: List[Tuple[int, float, int]]) -> None:
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
        for trigger_index, rel_seconds, sample_number in triggers:
            db.execute(
                "insert into triggers values (?, ?, ?, ?, 0, 0.0, 'estimated_fps', "
                "?, 0, 0, 'daq_sample_clock')",
                (trigger_index, f"t{trigger_index}", rel_seconds, sample_number, sample_number),
            )
        db.commit()


class TimestampMapperTest(unittest.TestCase):
    def test_matches_fps_formula_when_frames_are_uniform(self) -> None:
        coordinator = make_coordinator()
        seconds = uniform_seconds(1000)
        usable_start = 25
        mapper = coordinator._make_timestamp_mapper(seconds, usable_start)
        self.assertIsNotNone(mapper)
        for rel_seconds in (0.0, 1.0, 3.5, 10.0):
            frame_from_t0, video_frame = mapper(rel_seconds)
            # With perfectly uniform frames the timestamp lookup must agree with
            # the legacy 1 + round(rel * fps) model.
            self.assertEqual(frame_from_t0, 1 + round(rel_seconds * FPS))
            self.assertEqual(video_frame, usable_start + frame_from_t0 - 1)

    def test_burst_drop_does_not_drift_the_mapping(self) -> None:
        coordinator = make_coordinator()
        # 150 frames, a 3 s stall (~90 dropped frames), then 150 more frames.
        seconds = seconds_with_burst_drop(before=150, gap_seconds=3.0, after=150)
        usable_start = 1  # t0 == frame 1
        mapper = coordinator._make_timestamp_mapper(seconds, usable_start)
        self.assertIsNotNone(mapper)

        rel_seconds = 9.0  # well past the stall
        frame_from_t0, video_frame = mapper(rel_seconds)

        # Ground truth: the frame whose real capture time is closest to 9.0 s.
        expected_index = min(range(len(seconds)), key=lambda k: abs(seconds[k] - rel_seconds))
        self.assertEqual(video_frame, expected_index + 1)

        # The legacy linear model would land many frames away (it smears the
        # stall across the whole recording).
        measured_fps = (len(seconds) - 1) / (seconds[-1] - seconds[0])
        fps_frame = 1 + round(rel_seconds * measured_fps)
        self.assertGreater(abs(fps_frame - video_frame), 20)

    def test_returns_none_when_t0_frame_not_covered(self) -> None:
        coordinator = make_coordinator()
        seconds = uniform_seconds(10)
        self.assertIsNone(coordinator._make_timestamp_mapper(seconds, usable_start=50))


class RewriteWithTimestampsTest(unittest.TestCase):
    def test_rewrite_prefers_timestamps_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            coordinator = make_coordinator()
            seconds = seconds_with_burst_drop(before=150, gap_seconds=3.0, after=150)
            write_frame_times(output_dir / "mrc_recording_frame_times.csv", seconds)
            make_triggers_db(output_dir / "triggers.sqlite3", [(1, 9.0, 45000)])

            alignment = {
                "effective_fps": (len(seconds) - 1) / (seconds[-1] - seconds[0]),
                "usable_video_frame_start": 1,
                "target_end_sample": 10_000_000,
                "files": {"source_video": "mrc_recording.mp4"},
            }
            coordinator._rewrite_trigger_frames(output_dir, alignment)

            self.assertEqual(alignment["frame_mapping_mode"], "measured_timestamps")
            expected_index = min(range(len(seconds)), key=lambda k: abs(seconds[k] - 9.0))
            with closing(sqlite3.connect(output_dir / "triggers.sqlite3")) as db:
                (mode, video_frame) = db.execute(
                    "select frame_mapping_mode, video_frame_index_estimated from triggers"
                ).fetchone()
            self.assertEqual(mode, "measured_timestamps")
            self.assertEqual(video_frame, expected_index + 1)

    def test_rewrite_falls_back_to_fps_without_frame_times(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            coordinator = make_coordinator()
            make_triggers_db(output_dir / "triggers.sqlite3", [(1, 10.0, 50000)])
            alignment = {
                "effective_fps": 29.8,
                "usable_video_frame_start": 150,
                "target_end_sample": 2_400_000,
                "files": {"source_video": "mrc_recording.mp4"},
            }
            coordinator._rewrite_trigger_frames(output_dir, alignment)

            self.assertEqual(alignment["frame_mapping_mode"], "measured_fps")
            expected_frame = 1 + round(10.0 * 29.8)
            with closing(sqlite3.connect(output_dir / "triggers.sqlite3")) as db:
                (mode, frame_from_t0) = db.execute(
                    "select frame_mapping_mode, frame_index_from_t0 from triggers"
                ).fetchone()
            self.assertEqual(mode, "measured_fps")
            self.assertEqual(frame_from_t0, expected_frame)


class FrameTimingDiagnosticsTest(unittest.TestCase):
    def test_reports_and_locates_drops(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            coordinator = make_coordinator()
            seconds = seconds_with_burst_drop(before=150, gap_seconds=3.0, after=150)
            write_frame_times(output_dir / "mrc_recording_frame_times.csv", seconds)
            alignment = {
                "usable_video_frame_start": 1,
                "expected_total_frames": len(seconds),
                "t0_sample_number": 0,
                "sample_rate_hz": 5000,
                "files": {"source_video": "mrc_recording.mp4"},
            }
            coordinator._apply_frame_timing_diagnostics(output_dir, alignment)

            timing = alignment["frame_timing"]
            self.assertEqual(timing["status"], "ok")
            self.assertEqual(timing["frame_count"], len(seconds))
            self.assertGreaterEqual(timing["drop_event_count"], 1)
            # A 3 s stall at 30 fps ~= 90 dropped frames.
            self.assertAlmostEqual(timing["dropped_frames_estimate"], 90, delta=3)
            self.assertEqual(timing["drop_events"][0]["after_video_frame_index"], 150)

            # frame_map.csv is now truthful: its relative times must match the
            # real per-frame timestamps, not a uniform 1/fps grid.
            with (output_dir / "frame_map.csv").open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), len(seconds))
            self.assertAlmostEqual(float(rows[-1]["relative_time_seconds"]), seconds[-1], places=6)

    def test_unavailable_without_frame_times(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            coordinator = make_coordinator()
            alignment = {"files": {"source_video": "mrc_recording.mp4"}}
            coordinator._apply_frame_timing_diagnostics(output_dir, alignment)
            self.assertEqual(alignment["frame_timing"]["status"], "unavailable")


class Camera2SymmetryTest(unittest.TestCase):
    """Camera 2 must get the same measured-timestamp alignment as camera 1."""

    def test_camera2_gets_measured_frame_map_and_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            coordinator = make_coordinator()
            seconds = seconds_with_burst_drop(before=100, gap_seconds=2.0, after=100)
            write_frame_times(output_dir / "mrc_recording_camera2_frame_times.csv", seconds)
            cam2: dict = {}
            files: dict = {}
            coordinator._apply_frame_timing_diagnostics_for(
                output_dir,
                source_video_name="mrc_recording_camera2.mp4",
                usable_video_frame_start=1,
                expected_total_frames=len(seconds),
                t0_sample_number=0,
                sample_rate_hz=5000,
                target=cam2,
                files_dict=files,
                files_key="frame_times_camera2",
                frame_map_name="frame_map_camera2.csv",
            )
            self.assertEqual(cam2["frame_timing"]["status"], "ok")
            self.assertEqual(cam2["frame_mapping_mode"], "measured_timestamps")
            self.assertGreaterEqual(cam2["frame_timing"]["drop_event_count"], 1)
            self.assertEqual(files["frame_times_camera2"], "mrc_recording_camera2_frame_times.csv")
            fm = output_dir / "frame_map_camera2.csv"
            self.assertTrue(fm.exists())
            with fm.open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), len(seconds))
            self.assertAlmostEqual(float(rows[-1]["relative_time_seconds"]), seconds[-1], places=6)

    def test_camera2_falls_back_without_frame_times(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            coordinator = make_coordinator()
            cam2: dict = {}
            files: dict = {}
            coordinator._apply_frame_timing_diagnostics_for(
                output_dir,
                source_video_name="mrc_recording_camera2.mp4",
                usable_video_frame_start=1,
                expected_total_frames=100,
                t0_sample_number=0,
                sample_rate_hz=5000,
                target=cam2,
                files_dict=files,
                files_key="frame_times_camera2",
                frame_map_name="frame_map_camera2.csv",
            )
            self.assertEqual(cam2["frame_timing"]["status"], "unavailable")
            self.assertEqual(cam2["frame_mapping_mode"], "measured_fps")
            self.assertFalse((output_dir / "frame_map_camera2.csv").exists())


if __name__ == "__main__":
    unittest.main()

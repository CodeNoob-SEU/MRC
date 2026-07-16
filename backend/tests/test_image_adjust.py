import subprocess
import tempfile
import unittest
from pathlib import Path

from mrc_backend.config import AppConfig
from mrc_backend.events import EventBus
from mrc_backend.experiment import ExperimentCoordinator, ImageAdjustSettings


def make_coordinator() -> ExperimentCoordinator:
    config = AppConfig()
    config.hardware_mode = "mock"
    return ExperimentCoordinator(config, Path.cwd(), EventBus())


class ImageAdjustTest(unittest.TestCase):
    def test_identity_settings_produce_no_filter(self) -> None:
        coordinator = make_coordinator()
        self.assertIsNone(coordinator._build_adjust_video_filter(ImageAdjustSettings()))

    def test_filter_string_matches_preview_semantics(self) -> None:
        coordinator = make_coordinator()
        settings = ImageAdjustSettings(brightness=1.2, contrast=1.1, gamma=1.4, saturation=1.3, sharpness=0.5)
        video_filter = coordinator._build_adjust_video_filter(settings)
        assert video_filter is not None
        # eq contrast = b*c, brightness shift = 0.5*c*(b-1)
        self.assertIn("eq=contrast=1.3200:brightness=0.1100:gamma=1.4000:saturation=1.3000", video_filter)
        self.assertIn("unsharp=5:5:0.750", video_filter)

    def test_set_image_adjust_targets_and_clamps(self) -> None:
        coordinator = make_coordinator()
        result = coordinator.set_image_adjust(
            target="cam1",
            write_to_video=True,
            settings=ImageAdjustSettings(brightness=9.0, saturation=9.0),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(coordinator._image_adjust[1].brightness, 4.0)  # clamped
        self.assertEqual(coordinator._image_adjust[1].saturation, 3.0)  # eq filter limit
        self.assertTrue(coordinator._image_adjust[2].is_identity())  # non-target reset
        self.assertTrue(coordinator._adjust_write_to_video)

        coordinator.set_image_adjust(target="both", write_to_video=False, settings=ImageAdjustSettings(gamma=1.5))
        self.assertEqual(coordinator._image_adjust[2].gamma, 1.5)
        self.assertFalse(coordinator._adjust_write_to_video)

        with self.assertRaises(ValueError):
            coordinator.set_image_adjust(target="cam9", write_to_video=False, settings=ImageAdjustSettings())

    def test_adjust_filter_requires_write_flag(self) -> None:
        coordinator = make_coordinator()
        coordinator.set_image_adjust(target="both", write_to_video=False, settings=ImageAdjustSettings(gamma=1.5))
        self.assertIsNone(coordinator._adjust_filter_for_camera(1))
        coordinator.set_image_adjust(target="both", write_to_video=True, settings=ImageAdjustSettings(gamma=1.5))
        self.assertIsNotNone(coordinator._adjust_filter_for_camera(1))

    def test_trim_injects_video_filter_into_reencode_command(self) -> None:
        coordinator = make_coordinator()
        captured: list = []

        def fake_run(command, timeout):
            captured.append(list(command))
            Path(command[-1]).write_bytes(b"fake video")
            return subprocess.CompletedProcess(command, 0, "", "")

        coordinator._run_tracked = fake_run  # type: ignore[method-assign]
        coordinator._resolve_ffmpeg_executable = lambda: "ffmpeg"  # type: ignore[method-assign]
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "src.mp4"
            source.write_bytes(b"source video")
            result = coordinator._trim_video_from_t0(
                source_video=source,
                output_video=Path(temp_dir) / "out.mp4",
                start_seconds=1.0,
                duration_seconds=2.0,
                video_filter="eq=contrast=1.2000",
            )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["video_filter"], "eq=contrast=1.2000")
        command = captured[0]
        self.assertIn("-vf", command)
        self.assertEqual(command[command.index("-vf") + 1], "eq=contrast=1.2000")


if __name__ == "__main__":
    unittest.main()

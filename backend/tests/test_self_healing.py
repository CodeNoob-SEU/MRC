import time
import unittest
from pathlib import Path
from typing import Optional

from mrc_backend.config import AppConfig
from mrc_backend.events import EventBus
from mrc_backend.experiment import ExperimentCoordinator
from mrc_backend.hardware.camera import MockCamera


class DeadCamera(MockCamera):
    """Camera whose reconnect keeps failing until `revive` is set."""

    def __init__(self) -> None:
        super().__init__()
        self.reconnect_attempts = 0
        self.revive = False

    def reconnect(self):
        self.reconnect_attempts += 1
        if not self.revive:
            raise RuntimeError("simulated dead camera")
        return super().reconnect()


class TinyFrameCamera(MockCamera):
    """Simulates the green-screen wedge: valid JPEG data URL, tiny payload."""

    def preview_frame_data_url(self) -> Optional[str]:
        return "data:image/jpeg;base64," + "A" * 100


def make_coordinator(**config_overrides) -> ExperimentCoordinator:
    config = AppConfig()
    config.hardware_mode = "mock"
    for key, value in config_overrides.items():
        setattr(config, key, value)
    return ExperimentCoordinator(config, Path.cwd(), EventBus())


class SelfHealingTest(unittest.TestCase):
    def test_device_reset_runs_before_reconnect(self) -> None:
        # This hardware wedges its driver on hot-plug, so a plain reconnect
        # always fails; the PnP reset must run FIRST to unblock it.
        coordinator = make_coordinator()
        camera = DeadCamera()
        events: list = []

        def fake_reset(camera_id: int) -> bool:
            events.append("reset")
            camera.revive = True  # the reset "fixes" the device
            return True

        original_reconnect = camera.reconnect

        def tracking_reconnect():
            events.append("reconnect")
            return original_reconnect()

        camera.reconnect = tracking_reconnect  # type: ignore[method-assign]
        coordinator._attempt_device_reset = fake_reset  # type: ignore[method-assign]
        try:
            # First attempt already recovers: reset up front, then one reconnect.
            self.assertTrue(coordinator._try_reconnect_camera(1, camera))
            self.assertEqual(events, ["reset", "reconnect"])  # reset BEFORE reconnect
            self.assertEqual(coordinator._reconnect_failures[1], 0)
        finally:
            coordinator.close()

    def test_tiny_jpeg_preview_triggers_auto_reconnect(self) -> None:
        coordinator = make_coordinator()
        coordinator._preview_min_jpeg_bytes = 4096
        camera = TinyFrameCamera()
        reconnects: list = []
        coordinator._try_reconnect_camera = (  # type: ignore[method-assign]
            lambda camera_id, cam: reconnects.append(camera_id) or True
        )
        coordinator.camera = camera
        try:
            coordinator.initialize()
            deadline = time.time() + 5
            while time.time() < deadline and not reconnects:
                time.sleep(0.05)
            self.assertGreaterEqual(len(reconnects), 1)
        finally:
            coordinator.close()

    def test_mock_svg_preview_is_not_flagged_as_tiny(self) -> None:
        coordinator = make_coordinator()
        coordinator._preview_min_jpeg_bytes = 4096
        reconnects: list = []
        coordinator._try_reconnect_camera = (  # type: ignore[method-assign]
            lambda camera_id, cam: reconnects.append(camera_id) or True
        )
        try:
            coordinator.initialize()
            time.sleep(1.0)
            self.assertEqual(reconnects, [])
        finally:
            coordinator.close()

    def test_recover_camera_reports_next_steps_when_everything_fails(self) -> None:
        coordinator = make_coordinator()
        camera = DeadCamera()
        coordinator.camera = camera
        coordinator._attempt_device_reset = lambda camera_id: False  # type: ignore[method-assign]
        try:
            with self.assertRaises(RuntimeError) as ctx:
                coordinator.recover_camera(1)
            self.assertIn("拔插", str(ctx.exception))
        finally:
            coordinator.close()

    def test_recover_camera_rejected_while_recording(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            coordinator = make_coordinator(output_root=temp_dir)
            try:
                coordinator.initialize()
                coordinator.start_manual_recording()
                with self.assertRaises(RuntimeError):
                    coordinator.recover_camera(1)
                coordinator.stop_experiment()
            finally:
                coordinator.close()


if __name__ == "__main__":
    unittest.main()

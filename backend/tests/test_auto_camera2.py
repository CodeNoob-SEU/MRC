import unittest
from pathlib import Path
from unittest.mock import patch

from mrc_backend.config import AppConfig
from mrc_backend.events import EventBus
from mrc_backend.experiment import ExperimentCoordinator
from mrc_backend.hardware.camera import MockCamera


class TwoDeviceCamera(MockCamera):
    def initialize(self):
        status = super().initialize()
        self._status.device_count = 2
        return self.status()


def make_coordinator(camera2_auto: bool) -> ExperimentCoordinator:
    config = AppConfig()
    config.hardware_mode = "mock"
    config.camera2_auto = camera2_auto
    return ExperimentCoordinator(config, Path.cwd(), EventBus())


class AutoCamera2Test(unittest.TestCase):
    def test_second_camera_enabled_when_two_devices_detected(self) -> None:
        coordinator = make_coordinator(camera2_auto=True)
        coordinator.camera = TwoDeviceCamera()
        try:
            status = coordinator.initialize()
            self.assertIsNotNone(coordinator.camera2)
            self.assertTrue(status.camera2["initialized"])
            self.assertTrue(coordinator.devices()["camera2_enabled"])
            self.assertNotEqual(
                coordinator.config.camera2.device_index,
                coordinator.config.camera.device_index,
            )
        finally:
            coordinator.close()

    def test_second_camera_stays_off_with_one_device(self) -> None:
        coordinator = make_coordinator(camera2_auto=True)
        try:
            status = coordinator.initialize()  # MockCamera reports 1 device
            self.assertIsNone(coordinator.camera2)
            self.assertIsNone(status.camera2)
        finally:
            coordinator.close()

    def test_auto_detection_disabled_when_explicitly_off(self) -> None:
        coordinator = make_coordinator(camera2_auto=False)
        coordinator.camera = TwoDeviceCamera()
        try:
            coordinator.initialize()
            self.assertIsNone(coordinator.camera2)
        finally:
            coordinator.close()

    def test_env_parsing_for_camera2_modes(self) -> None:
        with patch.dict("os.environ", {"MRC_HARDWARE_MODE": "mock"}, clear=True):
            config = AppConfig.from_env()
        self.assertFalse(config.camera2_enabled)
        self.assertTrue(config.camera2_auto)

        with patch.dict("os.environ", {"MRC_CAMERA2_ENABLED": "1"}, clear=True):
            config = AppConfig.from_env()
        self.assertTrue(config.camera2_enabled)
        self.assertFalse(config.camera2_auto)

        with patch.dict("os.environ", {"MRC_CAMERA2_ENABLED": "0"}, clear=True):
            config = AppConfig.from_env()
        self.assertFalse(config.camera2_enabled)
        self.assertFalse(config.camera2_auto)


if __name__ == "__main__":
    unittest.main()

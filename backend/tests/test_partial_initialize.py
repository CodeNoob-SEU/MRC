import tempfile
import unittest
from pathlib import Path

from mrc_backend.config import AppConfig, DaqConfig
from mrc_backend.events import EventBus
from mrc_backend.experiment import ExperimentCoordinator
from mrc_backend.hardware.camera import MockCamera
from mrc_backend.hardware.daq import DaqError, MockDaq


class MissingDaq(MockDaq):
    def __init__(self, config: DaqConfig) -> None:
        super().__init__(config)

    def initialize(self):
        raise DaqError("NO_USBDAQ: simulated missing DAQ card")


class BrokenCamera(MockCamera):
    def initialize(self):
        raise RuntimeError("simulated missing camera")


class PartialInitializeTest(unittest.TestCase):
    def test_initialize_without_daq_still_allows_manual_recording(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = AppConfig()
            config.hardware_mode = "mock"
            config.output_root = temp_dir
            coordinator = ExperimentCoordinator(config, Path.cwd(), EventBus())
            coordinator.daq = MissingDaq(config.daq)
            try:
                status = coordinator.initialize()
                self.assertTrue(status.camera["initialized"])
                self.assertFalse(status.daq["initialized"])
                self.assertIn("daq", status.last_error or "")
                self.assertIn("NO_USBDAQ", status.last_error or "")

                status = coordinator.start_manual_recording()
                self.assertEqual(status.state, "manual_recording")
                self.assertTrue(status.camera["recording"])

                status = coordinator.stop_experiment()
                self.assertEqual(status.state, "manual_stopped")
            finally:
                coordinator.close()

    def test_trigger_experiment_without_daq_fails_with_daq_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = AppConfig()
            config.hardware_mode = "mock"
            config.output_root = temp_dir
            coordinator = ExperimentCoordinator(config, Path.cwd(), EventBus())
            coordinator.daq = MissingDaq(config.daq)
            try:
                coordinator.initialize()
                with self.assertRaises(DaqError):
                    coordinator.start_experiment()
                # Cameras must not be left recording after the failed start.
                self.assertFalse(coordinator.camera.status().recording)
                # And manual recording still works afterwards.
                status = coordinator.start_manual_recording()
                self.assertEqual(status.state, "manual_recording")
                coordinator.stop_experiment()
            finally:
                coordinator.close()

    def test_initialize_raises_only_when_every_device_fails(self) -> None:
        config = AppConfig()
        config.hardware_mode = "mock"
        coordinator = ExperimentCoordinator(config, Path.cwd(), EventBus())
        coordinator.camera = BrokenCamera()
        coordinator.daq = MissingDaq(config.daq)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                coordinator.initialize()
            self.assertIn("camera1", str(ctx.exception))
            self.assertIn("daq", str(ctx.exception))
        finally:
            coordinator.close()


if __name__ == "__main__":
    unittest.main()

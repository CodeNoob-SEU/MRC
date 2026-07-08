import tempfile
import time
import unittest
from pathlib import Path
from typing import Optional

from mrc_backend.config import AppConfig, DaqConfig
from mrc_backend.events import EventBus
from mrc_backend.experiment import ExperimentCoordinator
from mrc_backend.hardware.camera import MockCamera
from mrc_backend.hardware.daq import DaqError, MockDaq


class FlakyCamera(MockCamera):
    def __init__(self) -> None:
        super().__init__()
        self.reconnect_count = 0
        self.failing = False

    def preview_frame_data_url(self) -> Optional[str]:
        if self.failing:
            raise RuntimeError("simulated camera drop")
        return super().preview_frame_data_url()

    def reconnect(self):
        self.reconnect_count += 1
        self.failing = False
        return super().reconnect()


class FlakyDaq(MockDaq):
    def __init__(self, config: DaqConfig) -> None:
        super().__init__(config)
        self.reconnect_count = 0
        self.fail_reads = False

    def read_batch(self):
        if self.fail_reads:
            raise DaqError("simulated DAQ drop")
        return super().read_batch()

    def reconnect(self):
        self.reconnect_count += 1
        self.fail_reads = False
        return super().reconnect()


class AutoReconnectTest(unittest.TestCase):
    def test_camera_auto_reconnects_after_repeated_preview_failures(self) -> None:
        config = AppConfig()
        config.hardware_mode = "mock"
        config.camera.preview_fps = 60.0
        coordinator = ExperimentCoordinator(config, Path.cwd(), EventBus())
        camera = FlakyCamera()
        coordinator.camera = camera
        try:
            coordinator.initialize()
            camera.failing = True
            deadline = time.time() + 5
            while time.time() < deadline and camera.reconnect_count == 0:
                time.sleep(0.05)
            self.assertGreaterEqual(camera.reconnect_count, 1)
            self.assertFalse(camera.failing)
            self.assertTrue(camera.status().initialized)
        finally:
            coordinator.close()

    def test_camera_is_not_reconnected_while_recording(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = AppConfig()
            config.hardware_mode = "mock"
            config.output_root = temp_dir
            config.camera.preview_fps = 60.0
            config.window_minutes = 1.0
            coordinator = ExperimentCoordinator(config, Path.cwd(), EventBus())
            camera = FlakyCamera()
            coordinator.camera = camera
            try:
                coordinator.initialize()
                coordinator.start_experiment()
                camera.failing = True
                time.sleep(1.0)
                self.assertEqual(camera.reconnect_count, 0)
            finally:
                coordinator.close()

    def test_daq_auto_recovers_after_read_failure_during_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = AppConfig()
            config.hardware_mode = "mock"
            config.output_root = temp_dir
            config.daq.batch_points = 50
            coordinator = ExperimentCoordinator(config, Path.cwd(), EventBus())
            daq = FlakyDaq(config.daq)
            coordinator.daq = daq
            try:
                coordinator.initialize()
                daq.fail_reads = True
                coordinator.start_experiment()
                deadline = time.time() + 5
                while time.time() < deadline and daq.reconnect_count == 0:
                    time.sleep(0.05)
                self.assertGreaterEqual(daq.reconnect_count, 1)
                self.assertEqual(coordinator.status().state, "error")
                self.assertTrue(daq.status().initialized)
                self.assertFalse(daq.fail_reads)
            finally:
                coordinator.close()

    def test_daq_start_retries_once_after_reconnect(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = AppConfig()
            config.hardware_mode = "mock"
            config.output_root = temp_dir
            coordinator = ExperimentCoordinator(config, Path.cwd(), EventBus())

            class FailingStartDaq(FlakyDaq):
                def __init__(self, daq_config: DaqConfig) -> None:
                    super().__init__(daq_config)
                    self.start_attempts = 0

                def start_sampling(self):
                    self.start_attempts += 1
                    if self.start_attempts == 1:
                        raise DaqError("simulated start failure")
                    return super().start_sampling()

            daq = FailingStartDaq(config.daq)
            coordinator.daq = daq
            try:
                coordinator.initialize()
                status = coordinator.start_experiment()
                self.assertEqual(status.state, "armed")
                self.assertEqual(daq.reconnect_count, 1)
                self.assertEqual(daq.start_attempts, 2)
                coordinator.stop_experiment()
            finally:
                coordinator.close()


if __name__ == "__main__":
    unittest.main()

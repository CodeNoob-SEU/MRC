import tempfile
import unittest
from collections import namedtuple
from pathlib import Path
from unittest.mock import patch

from mrc_backend.config import AppConfig
from mrc_backend.events import EventBus
from mrc_backend.experiment import ExperimentCoordinator

DiskUsage = namedtuple("DiskUsage", "total used free")


class ProductionHardeningTest(unittest.TestCase):
    def test_start_experiment_rejected_when_disk_is_nearly_full(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = AppConfig()
            config.hardware_mode = "mock"
            config.output_root = temp_dir
            coordinator = ExperimentCoordinator(config, Path.cwd(), EventBus())
            try:
                coordinator.initialize()
                tiny = DiskUsage(total=100 * 1024 ** 3, used=100 * 1024 ** 3, free=100 * 1024 ** 2)
                with patch("mrc_backend.experiment.shutil.disk_usage", return_value=tiny):
                    with self.assertRaises(RuntimeError) as ctx:
                        coordinator.start_experiment()
                self.assertIn("磁盘剩余空间不足", str(ctx.exception))
                # Cameras must not be left recording after the rejected start.
                self.assertFalse(coordinator.camera.status().recording)
                # And with enough space the experiment starts normally.
                status = coordinator.start_experiment()
                self.assertEqual(status.state, "armed")
                coordinator.stop_experiment()
            finally:
                coordinator.close()

    def test_event_bus_publish_survives_closed_loop(self) -> None:
        bus = EventBus()

        class ClosedLoop:
            def call_soon_threadsafe(self, callback):
                raise RuntimeError("Event loop is closed")

        bus._loop = ClosedLoop()  # type: ignore[assignment]
        bus.publish("status", {"state": "idle"})  # must not raise


if __name__ == "__main__":
    unittest.main()

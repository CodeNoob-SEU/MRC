import tempfile
import time
import unittest
from pathlib import Path

from mrc_backend.config import AppConfig
from mrc_backend.events import EventBus
from mrc_backend.experiment import ExperimentCoordinator


class CoordinatorMockTest(unittest.TestCase):
    def test_mock_experiment_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = AppConfig()
            config.hardware_mode = "mock"
            config.output_root = temp_dir
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


if __name__ == "__main__":
    unittest.main()

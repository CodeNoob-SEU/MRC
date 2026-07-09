import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from mrc_backend.config import CameraConfig
from mrc_backend.hardware.camera import CameraError
from mrc_backend.hardware.camera_process import (
    _WORKER_PIDFILE_DIR,
    CameraProcessProxy,
    sweep_stale_camera_workers,
)


def make_proxy(factory_name: str, timeout_overrides=None) -> CameraProcessProxy:
    return CameraProcessProxy(
        CameraConfig(),
        Path.cwd(),
        factory=("tests.camera_worker_stubs", factory_name),
        timeout_overrides=timeout_overrides,
    )


class CameraProcessProxyTest(unittest.TestCase):
    def test_full_lifecycle_through_worker_process(self) -> None:
        proxy = make_proxy("make_mock_camera")
        try:
            status = proxy.initialize()
            self.assertTrue(status.initialized)
            self.assertTrue(proxy.status().initialized)
            worker_pid = proxy._proc.pid
            self.assertNotEqual(worker_pid, os.getpid())

            with tempfile.TemporaryDirectory() as temp_dir:
                output = Path(temp_dir) / "clip.mp4"
                status = proxy.start_recording(output)
                self.assertTrue(status.recording)
                self.assertTrue(output.exists())  # written by the child process
                frame = proxy.preview_frame_data_url()
                self.assertTrue(frame and frame.startswith("data:image/"))
                status = proxy.stop_recording()
                self.assertFalse(status.recording)

            devices = proxy.enumerate_devices()
            self.assertEqual(devices[0]["device_name"], "Mock MRC camera")
        finally:
            proxy.close()
        deadline = time.time() + 5
        while time.time() < deadline and proxy._proc is not None:
            time.sleep(0.05)
        self.assertIsNone(proxy._proc)

    def test_wedged_preview_times_out_and_reconnect_respawns_worker(self) -> None:
        proxy = make_proxy(
            "make_blocking_preview_camera",
            timeout_overrides={"preview_frame_data_url": 0.5},
        )
        try:
            proxy.initialize()
            old_proc = proxy._proc
            with self.assertRaises(CameraError):
                proxy.preview_frame_data_url()
            # Preview timeout alone must not kill the worker.
            self.assertTrue(old_proc.is_alive())

            status = proxy.reconnect()
            self.assertTrue(status.initialized)
            self.assertNotEqual(proxy._proc.pid, old_proc.pid)
            self.assertFalse(old_proc.is_alive())
        finally:
            proxy.close()

    def test_wedged_stop_recording_terminates_worker_and_stays_bounded(self) -> None:
        proxy = make_proxy(
            "make_blocking_stop_camera",
            timeout_overrides={"stop_recording": 0.5},
        )
        try:
            proxy.initialize()
            with tempfile.TemporaryDirectory() as temp_dir:
                proxy.start_recording(Path(temp_dir) / "clip.mp4")
                started = time.monotonic()
                with self.assertRaises(CameraError):
                    proxy.stop_recording()
                self.assertLess(time.monotonic() - started, 5.0)
            # Control-call timeout means the SDK wedged: worker abandoned.
            self.assertIsNone(proxy._proc)
            self.assertFalse(proxy.status().initialized)
            # And the camera comes back on a fresh worker.
            status = proxy.initialize()
            self.assertTrue(status.initialized)
        finally:
            proxy.close()

    def test_dead_worker_raises_then_initialize_respawns(self) -> None:
        proxy = make_proxy("make_mock_camera")
        try:
            proxy.initialize()
            proxy._proc.terminate()
            proxy._proc.join(timeout=5)
            with self.assertRaises(CameraError):
                proxy.stop_recording()
            status = proxy.initialize()
            self.assertTrue(status.initialized)
        finally:
            proxy.close()

    def test_sweep_removes_dead_worker_pidfiles(self) -> None:
        _WORKER_PIDFILE_DIR.mkdir(parents=True, exist_ok=True)
        stale = _WORKER_PIDFILE_DIR / "999999999.json"
        stale.write_text(
            json.dumps({"pid": 999999999, "backend_pid": 999999998, "created_at": 0}),
            encoding="utf-8",
        )
        sweep_stale_camera_workers()
        self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()

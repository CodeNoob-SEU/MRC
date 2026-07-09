"""Camera factories importable by the spawned camera worker in tests."""

from __future__ import annotations

import time
from pathlib import Path

from mrc_backend.config import CameraConfig
from mrc_backend.hardware.camera import BaseCamera, MockCamera


class BlockingPreviewCamera(MockCamera):
    """Simulates a vendor DLL that wedges inside the preview call."""

    def preview_frame_data_url(self):
        time.sleep(120)
        return None


class BlockingStopCamera(MockCamera):
    """Simulates a vendor DLL that wedges inside DXStopCapture."""

    def stop_recording(self):
        time.sleep(120)
        return super().stop_recording()


def make_mock_camera(config: CameraConfig, repo_root: Path) -> BaseCamera:
    return MockCamera()


def make_blocking_preview_camera(config: CameraConfig, repo_root: Path) -> BaseCamera:
    return BlockingPreviewCamera()


def make_blocking_stop_camera(config: CameraConfig, repo_root: Path) -> BaseCamera:
    return BlockingStopCamera()

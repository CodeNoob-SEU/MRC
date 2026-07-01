from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import os


@dataclass
class CameraConfig:
    device_index: int = 0
    fps: float = 30.0
    width: int = 720
    height: int = 480
    video_standard: int = 1
    colorspace: int = 2
    save_audio: bool = True
    capture_format: int = 2
    video_codec: str = "x264 Codec"
    video_source_index: int = 0
    preview_mode: int = 2
    preview_fps: float = 12.0
    dxmedia_dll: str = "vendor/camera/x64/DXMediaCap.dll"


@dataclass
class DaqConfig:
    device_index: int = 0
    trigger_channel: int = 0
    sample_rate_hz: int = 5000
    sample_period: int = 200000
    batch_points: int = 500
    timeout_ms: int = 4000
    ai_range: float = 10.24
    threshold_volts: float = 2.5
    debounce_seconds: float = 0.010
    usb3000_dll: str = "vendor/daq/x64/USB3000.dll"
    mock_trigger_interval_seconds: float = 2.0


@dataclass
class AppConfig:
    hardware_mode: str = "mock"
    host: str = "127.0.0.1"
    port: int = 7876
    output_root: str = "runs"
    window_minutes: float = 6.0
    camera: CameraConfig = field(default_factory=CameraConfig)
    daq: DaqConfig = field(default_factory=DaqConfig)

    @classmethod
    def from_env(cls) -> "AppConfig":
        config = cls()
        config.hardware_mode = os.getenv("MRC_HARDWARE_MODE", config.hardware_mode)
        config.host = os.getenv("MRC_BACKEND_HOST", config.host)
        config.port = int(os.getenv("MRC_BACKEND_PORT", str(config.port)))
        config.output_root = os.getenv("MRC_OUTPUT_ROOT", config.output_root)
        vendor_arch = os.getenv("MRC_VENDOR_ARCH", "").lower()
        if vendor_arch in {"win32", "x86", "32"}:
            config.camera.dxmedia_dll = "vendor/camera/win32/DXMediaCap.dll"
            config.daq.usb3000_dll = "vendor/daq/x86/USB3000.dll"
        elif vendor_arch in {"x64", "amd64", "64"}:
            config.camera.dxmedia_dll = "vendor/camera/x64/DXMediaCap.dll"
            config.daq.usb3000_dll = "vendor/daq/x64/USB3000.dll"
        config.camera.device_index = int(os.getenv("MRC_CAMERA_DEVICE_INDEX", str(config.camera.device_index)))
        config.camera.width = int(os.getenv("MRC_CAMERA_WIDTH", str(config.camera.width)))
        config.camera.height = int(os.getenv("MRC_CAMERA_HEIGHT", str(config.camera.height)))
        config.camera.fps = float(os.getenv("MRC_CAMERA_FPS", str(config.camera.fps)))
        config.camera.video_standard = int(os.getenv("MRC_CAMERA_VIDEO_STANDARD", str(config.camera.video_standard)))
        config.camera.colorspace = int(os.getenv("MRC_CAMERA_COLORSPACE", str(config.camera.colorspace)))
        config.camera.capture_format = int(os.getenv("MRC_CAMERA_CAPTURE_FORMAT", str(config.camera.capture_format)))
        config.camera.video_codec = os.getenv("MRC_CAMERA_VIDEO_CODEC", config.camera.video_codec)
        config.camera.video_source_index = int(
            os.getenv("MRC_CAMERA_VIDEO_SOURCE_INDEX", str(config.camera.video_source_index))
        )
        config.camera.preview_mode = int(os.getenv("MRC_CAMERA_PREVIEW_MODE", str(config.camera.preview_mode)))
        config.camera.preview_fps = float(os.getenv("MRC_CAMERA_PREVIEW_FPS", str(config.camera.preview_fps)))
        config.camera.save_audio = os.getenv("MRC_CAMERA_SAVE_AUDIO", str(config.camera.save_audio)).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        config.daq.device_index = int(os.getenv("MRC_DAQ_DEVICE_INDEX", str(config.daq.device_index)))
        config.camera.dxmedia_dll = os.getenv("MRC_DXMEDIA_DLL", config.camera.dxmedia_dll)
        config.daq.usb3000_dll = os.getenv("MRC_USB3000_DLL", config.daq.usb3000_dll)
        return config

    def to_dict(self) -> dict:
        return asdict(self)

    def write_snapshot(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def resolve_path(path_text: str, base_dir: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()

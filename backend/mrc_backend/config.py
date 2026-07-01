from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import os


@dataclass(slots=True)
class CameraConfig:
    device_index: int = 0
    fps: float = 40.0
    width: int = 720
    height: int = 576
    video_standard: int = 32
    colorspace: int = 2
    save_audio: bool = False
    dxmedia_dll: str = "vendor/camera/x64/DXMediaCap.dll"


@dataclass(slots=True)
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


@dataclass(slots=True)
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

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
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
    preview_fps: float = 0.0
    dxmedia_dll: str = "vendor/camera/x64/DXMediaCap.dll"
    # Capture pipeline:
    #   "dll"       - vendor DXStartCapture: the DLL encodes+writes a CFR mp4;
    #                 dropped frames are silent and the timeline drifts.
    #   "selfbuilt" - raw-frame callback -> our own ffmpeg encoder, recording an
    #                 exact monotonic timestamp per written frame (frame_times.csv)
    #                 so alignment maps DAQ triggers to the real frame with no
    #                 interpolation. Fails safe: falls back to "dll" on any error.
    # ("selfbuilt" is video-only; the DLL's audio path is not used.)
    capture_mode: str = "dll"


@dataclass
class DaqConfig:
    device_index: int = 0
    trigger_channel: int = 0
    sample_rate_hz: int = 5000
    sample_period: int = 200000
    batch_points: int = 500
    # One batch is 100 ms of data at 5 kHz; keep this bounded so an in-flight
    # USB3GetAi never delays shutdown for long (close waits for it to finish).
    timeout_ms: int = 1000
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
    post_window_record_seconds: float = 1.0
    video_trim_enabled: bool = True
    video_trim_mode: str = "reencode"
    ffmpeg_path: str = ""
    camera2_enabled: bool = False
    # When true, camera 2 is enabled automatically at initialize time if the
    # SDK reports two or more capture devices.
    camera2_auto: bool = False
    camera: CameraConfig = field(default_factory=CameraConfig)
    camera2: CameraConfig = field(default_factory=CameraConfig)
    daq: DaqConfig = field(default_factory=DaqConfig)

    @classmethod
    def from_env(cls) -> "AppConfig":
        config = cls()
        config.hardware_mode = os.getenv("MRC_HARDWARE_MODE", config.hardware_mode)
        config.host = os.getenv("MRC_BACKEND_HOST", config.host)
        config.port = int(os.getenv("MRC_BACKEND_PORT", str(config.port)))
        config.output_root = os.getenv("MRC_OUTPUT_ROOT", config.output_root)
        config.post_window_record_seconds = float(
            os.getenv("MRC_POST_WINDOW_RECORD_SECONDS", str(config.post_window_record_seconds))
        )
        config.video_trim_enabled = os.getenv(
            "MRC_VIDEO_TRIM_ENABLED",
            str(config.video_trim_enabled),
        ).lower() in {"1", "true", "yes", "on"}
        config.video_trim_mode = os.getenv("MRC_VIDEO_TRIM_MODE", config.video_trim_mode)
        config.ffmpeg_path = os.getenv("MRC_FFMPEG", config.ffmpeg_path)
        vendor_arch = os.getenv("MRC_VENDOR_ARCH", "").lower()
        if vendor_arch in {"win32", "x86", "32"}:
            config.camera.dxmedia_dll = "vendor/camera/win32/DXMediaCap.dll"
            config.camera2.dxmedia_dll = "vendor/camera/win32/DXMediaCap.dll"
            config.daq.usb3000_dll = "vendor/daq/x86/USB3000.dll"
        elif vendor_arch in {"x64", "amd64", "64"}:
            config.camera.dxmedia_dll = "vendor/camera/x64/DXMediaCap.dll"
            config.camera2.dxmedia_dll = "vendor/camera/x64/DXMediaCap.dll"
            config.daq.usb3000_dll = "vendor/daq/x64/USB3000.dll"
        config.camera = _camera_from_env(config.camera, "MRC_CAMERA")
        config.camera2 = replace(config.camera)
        config.camera2.device_index = int(
            os.getenv("MRC_CAMERA2_DEVICE_INDEX", str(config.camera.device_index + 1))
        )
        config.camera2 = _camera_from_env(config.camera2, "MRC_CAMERA2")
        camera2_raw = os.getenv("MRC_CAMERA2_ENABLED", "auto").strip().lower()
        if camera2_raw in {"1", "true", "yes", "on"}:
            config.camera2_enabled = True
            config.camera2_auto = False
        elif camera2_raw in {"0", "false", "no", "off"}:
            config.camera2_enabled = False
            config.camera2_auto = False
        else:  # "auto" or anything else: detect at initialize time
            config.camera2_enabled = False
            config.camera2_auto = True
        config.daq.device_index = int(os.getenv("MRC_DAQ_DEVICE_INDEX", str(config.daq.device_index)))
        config.camera.dxmedia_dll = os.getenv("MRC_DXMEDIA_DLL", config.camera.dxmedia_dll)
        config.camera2.dxmedia_dll = os.getenv(
            "MRC_CAMERA2_DXMEDIA_DLL",
            os.getenv("MRC_DXMEDIA_DLL", config.camera2.dxmedia_dll),
        )
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


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _camera_from_env(camera: CameraConfig, prefix: str) -> CameraConfig:
    camera.device_index = int(os.getenv(f"{prefix}_DEVICE_INDEX", str(camera.device_index)))
    camera.width = int(os.getenv(f"{prefix}_WIDTH", str(camera.width)))
    camera.height = int(os.getenv(f"{prefix}_HEIGHT", str(camera.height)))
    camera.fps = float(os.getenv(f"{prefix}_FPS", str(camera.fps)))
    camera.video_standard = int(os.getenv(f"{prefix}_VIDEO_STANDARD", str(camera.video_standard)))
    camera.colorspace = int(os.getenv(f"{prefix}_COLORSPACE", str(camera.colorspace)))
    camera.capture_format = int(os.getenv(f"{prefix}_CAPTURE_FORMAT", str(camera.capture_format)))
    camera.video_codec = os.getenv(f"{prefix}_VIDEO_CODEC", camera.video_codec)
    camera.video_source_index = int(os.getenv(f"{prefix}_VIDEO_SOURCE_INDEX", str(camera.video_source_index)))
    camera.preview_mode = int(os.getenv(f"{prefix}_PREVIEW_MODE", str(camera.preview_mode)))
    camera.preview_fps = float(os.getenv(f"{prefix}_PREVIEW_FPS", str(camera.preview_fps)))
    camera.save_audio = _env_bool(f"{prefix}_SAVE_AUDIO", camera.save_audio)
    camera.capture_mode = os.getenv(f"{prefix}_CAPTURE_MODE", camera.capture_mode).strip().lower()
    camera.dxmedia_dll = os.getenv(f"{prefix}_DXMEDIA_DLL", camera.dxmedia_dll)
    return camera

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import base64
import ctypes
import os
import platform
import tempfile
import time
from typing import Dict, List, Optional
from urllib.parse import quote

from ..config import CameraConfig, resolve_path


class CameraError(RuntimeError):
    pass


class DeviceTag(ctypes.Structure):
    _fields_ = [
        ("idx", ctypes.c_uint),
        ("deviceName", ctypes.c_char * 128),
    ]


def signed_u32(value: int) -> int:
    value = int(value) & 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def format_sdk_code(value: int) -> str:
    signed = signed_u32(value)
    unsigned = int(value) & 0xFFFFFFFF
    if signed == unsigned:
        return str(signed)
    return f"{signed} (unsigned={unsigned}, hex=0x{unsigned:08X})"


@dataclass
class CameraStatus:
    mode: str
    initialized: bool = False
    recording: bool = False
    device_count: int = 0
    device_name: str = ""
    frame_mapping_mode: str = "estimated_fps"
    active_file: Optional[str] = None


class BaseCamera:
    def initialize(self) -> CameraStatus:
        raise NotImplementedError

    def start_recording(self, output_file: Path) -> CameraStatus:
        raise NotImplementedError

    def stop_recording(self) -> CameraStatus:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def status(self) -> CameraStatus:
        raise NotImplementedError

    def preview_frame_data_url(self) -> Optional[str]:
        raise NotImplementedError


class MockCamera(BaseCamera):
    def __init__(self) -> None:
        self._status = CameraStatus(mode="mock")

    def initialize(self) -> CameraStatus:
        self._status.initialized = True
        self._status.device_count = 1
        self._status.device_name = "Mock MRC camera"
        return self.status()

    def start_recording(self, output_file: Path) -> CameraStatus:
        if not self._status.initialized:
            self.initialize()
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(
            f"Mock video placeholder created at {time.time():.3f}\n",
            encoding="utf-8",
        )
        self._status.recording = True
        self._status.active_file = str(output_file)
        return self.status()

    def stop_recording(self) -> CameraStatus:
        self._status.recording = False
        return self.status()

    def close(self) -> None:
        self._status.recording = False
        self._status.initialized = False

    def status(self) -> CameraStatus:
        return replace(self._status)

    def preview_frame_data_url(self) -> Optional[str]:
        now = time.time()
        phase = int((now * 10) % 360)
        active = "#1f6f62" if self._status.recording else "#456070"
        svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360">
          <defs>
            <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
              <stop offset="0" stop-color="#111820"/>
              <stop offset="1" stop-color="#2b3844"/>
            </linearGradient>
          </defs>
          <rect width="640" height="360" fill="url(#g)"/>
          <g stroke="#6d7b87" stroke-width="1" opacity="0.45">
            <path d="M0 90H640M0 180H640M0 270H640M160 0V360M320 0V360M480 0V360"/>
          </g>
          <circle cx="{120 + (phase % 400)}" cy="180" r="48" fill="{active}" opacity="0.82"/>
          <rect x="26" y="24" width="178" height="38" rx="6" fill="#f6f7f9" opacity="0.92"/>
          <text x="42" y="49" font-family="Segoe UI, Arial" font-size="18" fill="#18202a">MOCK CAMERA</text>
          <text x="42" y="324" font-family="Segoe UI, Arial" font-size="15" fill="#d9e0e7">
            {time.strftime("%H:%M:%S")} · {'REC' if self._status.recording else 'LIVE'}
          </text>
        </svg>
        """
        return "data:image/svg+xml;charset=utf-8," + quote(svg)

    def enumerate_devices(self) -> List[Dict[str, object]]:
        return [{"idx": 0, "device_name": "Mock MRC camera"}]


class DXMediaCamera(BaseCamera):
    def __init__(self, config: CameraConfig, repo_root: Path) -> None:
        self.config = config
        self.repo_root = repo_root
        self.dll_path = resolve_path(config.dxmedia_dll, repo_root)
        self._dll: Optional[ctypes.CDLL] = None
        self._handle: Optional[ctypes.c_void_p] = None
        self._status = CameraStatus(mode="real")
        self._runtime_dir_added = False

    def _load(self) -> ctypes.CDLL:
        if platform.system() != "Windows":
            raise CameraError("DXMediaCap.dll can only be loaded on Windows.")
        if not self.dll_path.exists():
            raise CameraError(f"DXMediaCap.dll not found: {self.dll_path}")
        if self._dll is None:
            if hasattr(os, "add_dll_directory") and not self._runtime_dir_added:
                os.add_dll_directory(str(self.dll_path.parent))
                self._runtime_dir_added = True
            os.chdir(self.dll_path.parent)
            win_dll = getattr(ctypes, "WinDLL", None)
            if win_dll is None:
                raise CameraError("ctypes.WinDLL is not available in this Python runtime.")
            self._dll = win_dll(str(self.dll_path))
            self._configure_signatures(self._dll)
        return self._dll

    @staticmethod
    def _configure_signatures(dll: ctypes.CDLL) -> None:
        dll.DXInitialize.restype = ctypes.c_uint
        dll.DXUninitialize.restype = None
        dll.DXGetDeviceCount.restype = ctypes.c_uint
        dll.DXEnumVideoDevices.argtypes = [ctypes.POINTER(DeviceTag), ctypes.POINTER(ctypes.c_uint)]
        dll.DXEnumVideoDevices.restype = ctypes.c_uint
        dll.DXOpenDevice.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_uint)]
        dll.DXOpenDevice.restype = ctypes.c_void_p
        dll.DXCloseDevice.argtypes = [ctypes.c_void_p]
        dll.DXCloseDevice.restype = None
        dll.DXGetDeviceName.argtypes = [ctypes.c_void_p]
        dll.DXGetDeviceName.restype = ctypes.c_char_p
        dll.DXSetVideoPara.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_float,
        ]
        dll.DXSetVideoPara.restype = ctypes.c_uint
        dll.DXDeviceRunEx.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_bool]
        dll.DXDeviceRunEx.restype = ctypes.c_uint
        dll.DXStartCapture.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint,
        ]
        dll.DXStartCapture.restype = ctypes.c_uint
        dll.DXStopCapture.argtypes = [ctypes.c_void_p]
        dll.DXStopCapture.restype = ctypes.c_uint
        dll.DXDeviceStop.argtypes = [ctypes.c_void_p]
        dll.DXDeviceStop.restype = ctypes.c_uint
        dll.DXSnapToJPGFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint, ctypes.c_void_p]
        dll.DXSnapToJPGFile.restype = ctypes.c_uint

    def enumerate_devices(self) -> List[Dict[str, object]]:
        dll = self._load()
        result = dll.DXInitialize()
        if result != 0:
            raise CameraError(f"DXInitialize failed with code {format_sdk_code(result)}")
        count = int(dll.DXGetDeviceCount())
        self._status.device_count = count
        max_devices = max(count, 16)
        tags = (DeviceTag * max_devices)()
        num = ctypes.c_uint(max_devices)
        enum_result = dll.DXEnumVideoDevices(tags, ctypes.byref(num))
        if enum_result != 0:
            raise CameraError(f"DXEnumVideoDevices failed with code {format_sdk_code(enum_result)}")
        devices: List[Dict[str, object]] = []
        for idx in range(int(num.value)):
            name = bytes(tags[idx].deviceName).split(b"\0", 1)[0].decode("mbcs", errors="replace")
            devices.append({"idx": int(tags[idx].idx), "device_name": name})
        return devices

    def initialize(self) -> CameraStatus:
        dll = self._load()
        result = dll.DXInitialize()
        if result != 0:
            raise CameraError(f"DXInitialize failed with code {format_sdk_code(result)}")
        count = int(dll.DXGetDeviceCount())
        self._status.device_count = count
        if count <= self.config.device_index:
            raise CameraError(f"Camera index {self.config.device_index} unavailable; count={count}")
        err = ctypes.c_uint(0)
        handle = dll.DXOpenDevice(self.config.device_index, ctypes.byref(err))
        if not handle or err.value != 0:
            devices = []
            try:
                devices = self.enumerate_devices()
            except Exception:
                devices = []
            raise CameraError(
                "DXOpenDevice failed with code "
                f"{format_sdk_code(err.value)}; device_count={count}; "
                f"selected_index={self.config.device_index}; devices={devices}; "
                "check that the camera is connected, the vendor demo can open it, "
                "and no other program is occupying it."
            )
        self._handle = ctypes.c_void_p(handle)
        name = dll.DXGetDeviceName(self._handle)
        self._status.initialized = True
        self._status.device_count = count
        self._status.device_name = name.decode("mbcs", errors="replace") if name else ""

        set_result = dll.DXSetVideoPara(
            self._handle,
            self.config.video_standard,
            self.config.colorspace,
            self.config.width,
            self.config.height,
            ctypes.c_float(self.config.fps),
        )
        if set_result != 0:
            raise CameraError(f"DXSetVideoPara failed with code {format_sdk_code(set_result)}")
        run_result = dll.DXDeviceRunEx(self._handle, False, False)
        if run_result != 0:
            raise CameraError(f"DXDeviceRunEx failed with code {format_sdk_code(run_result)}")
        return self.status()

    def start_recording(self, output_file: Path) -> CameraStatus:
        if self._handle is None:
            self.initialize()
        assert self._dll is not None
        output_file.parent.mkdir(parents=True, exist_ok=True)
        result = self._dll.DXStartCapture(
            self._handle,
            str(output_file).encode("mbcs", errors="replace"),
            int(self.config.save_audio),
            None,
            None,
            1,
        )
        if result != 0:
            raise CameraError(f"DXStartCapture failed with code {format_sdk_code(result)}")
        self._status.recording = True
        self._status.active_file = str(output_file)
        return self.status()

    def stop_recording(self) -> CameraStatus:
        if self._dll is not None and self._handle is not None and self._status.recording:
            result = self._dll.DXStopCapture(self._handle)
            if result != 0:
                raise CameraError(f"DXStopCapture failed with code {format_sdk_code(result)}")
        self._status.recording = False
        return self.status()

    def close(self) -> None:
        if self._dll is not None and self._handle is not None:
            if self._status.recording:
                self.stop_recording()
            self._dll.DXDeviceStop(self._handle)
            self._dll.DXCloseDevice(self._handle)
            self._handle = None
            self._dll.DXUninitialize()
        self._status.initialized = False
        self._status.recording = False

    def status(self) -> CameraStatus:
        return replace(self._status)

    def preview_frame_data_url(self) -> Optional[str]:
        if self._dll is None or self._handle is None or not self._status.initialized:
            return None
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        try:
            result = self._dll.DXSnapToJPGFile(
                self._handle,
                str(temp_path).encode("mbcs", errors="replace"),
                70,
                None,
            )
            if result != 0 or not temp_path.exists():
                return None
            encoded = base64.b64encode(temp_path.read_bytes()).decode("ascii")
            return f"data:image/jpeg;base64,{encoded}"
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def build_camera(mode: str, config: CameraConfig, repo_root: Path) -> BaseCamera:
    if mode == "real":
        return DXMediaCamera(config, repo_root)
    if mode == "auto" and platform.system() == "Windows":
        return DXMediaCamera(config, repo_root)
    return MockCamera()

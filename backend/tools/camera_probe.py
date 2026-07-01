from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


COINIT_APARTMENTTHREADED = 0x2
RPC_E_CHANGED_MODE = -2147417850
CS_RGB24 = 0
CS_RGB32 = 1
CS_YUY2 = 2
DP_OVERLAY = 0
DP_VMR9 = 1
DP_D3D = 2
DP_OFFSCREEN = 3
DP_SDL = 4
FILE_AVI = 1
FILE_MP4 = 2


class DeviceTag(ctypes.Structure):
    _fields_ = [
        ("idx", ctypes.c_uint),
        ("deviceName", ctypes.c_char * 128),
    ]


class Rect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


WINFUNCTYPE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)

RawVideoCallback = WINFUNCTYPE(
    ctypes.c_uint,
    ctypes.POINTER(ctypes.c_ubyte),
    ctypes.c_uint,
    ctypes.c_uint,
    ctypes.c_uint,
    ctypes.c_uint,
    ctypes.c_void_p,
)


def signed_u32(value: int) -> int:
    value = int(value) & 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def format_code(value: int) -> str:
    signed = signed_u32(value)
    unsigned = int(value) & 0xFFFFFFFF
    if signed == unsigned:
        return str(signed)
    return f"{signed} (unsigned={unsigned}, hex=0x{unsigned:08X})"


def decode_name(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("mbcs", errors="replace")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_dll_path(root: Path) -> Path:
    vendor_arch = os.getenv("MRC_VENDOR_ARCH", "win32").lower()
    if vendor_arch in {"x64", "amd64", "64"}:
        return root / "vendor" / "camera" / "x64" / "DXMediaCap.dll"
    return root / "vendor" / "camera" / "win32" / "DXMediaCap.dll"


def ensure_windows() -> None:
    if platform.system() != "Windows":
        raise RuntimeError("camera_probe.py must run on Windows because DXMediaCap.dll is a Windows SDK.")


def initialize_com() -> str:
    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    ole32.CoInitializeEx.restype = ctypes.c_long
    result = int(ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED))
    if result == 0:
        return "STA initialized"
    if result == 1:
        return "STA already initialized"
    if result == RPC_E_CHANGED_MODE:
        return "COM already initialized with a different apartment"
    raise RuntimeError(f"CoInitializeEx failed: {format_code(result)}")


def load_sdk(dll_path: Path) -> ctypes.CDLL:
    if not dll_path.exists():
        raise FileNotFoundError(f"DXMediaCap.dll not found: {dll_path}")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(dll_path.parent))
    os.chdir(str(dll_path.parent))
    dll = ctypes.WinDLL(str(dll_path))
    configure_signatures(dll)
    return dll


def configure_signatures(dll: ctypes.CDLL) -> None:
    dll.DXInitialize.restype = ctypes.c_uint
    dll.DXUninitialize.restype = None
    dll.DXGetDeviceCount.restype = ctypes.c_uint
    dll.DXEnumVideoDevices.argtypes = [ctypes.POINTER(DeviceTag), ctypes.POINTER(ctypes.c_uint)]
    dll.DXEnumVideoDevices.restype = ctypes.c_uint
    dll.DXEnumVideoCodecs.argtypes = [ctypes.POINTER(DeviceTag), ctypes.POINTER(ctypes.c_uint)]
    dll.DXEnumVideoCodecs.restype = ctypes.c_uint
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
    dll.DXGetVideoSources.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_ubyte),
    ]
    dll.DXGetVideoSources.restype = ctypes.c_uint
    dll.DXSetVideoSource.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    dll.DXSetVideoSource.restype = ctypes.c_uint
    dll.DXSetVideoSourceEx.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    dll.DXSetVideoSourceEx.restype = ctypes.c_uint
    dll.DXGetSignalPresent.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
    dll.DXGetSignalPresent.restype = ctypes.c_uint
    dll.DXSetVideoCodec.argtypes = [ctypes.c_void_p, ctypes.POINTER(DeviceTag)]
    dll.DXSetVideoCodec.restype = ctypes.c_uint
    dll.DXDeviceRun.argtypes = [ctypes.c_void_p]
    dll.DXDeviceRun.restype = ctypes.c_uint
    dll.DXDeviceRunEx.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_bool]
    dll.DXDeviceRunEx.restype = ctypes.c_uint
    dll.DXDeviceStop.argtypes = [ctypes.c_void_p]
    dll.DXDeviceStop.restype = ctypes.c_uint
    dll.DXStartPreview.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(Rect), ctypes.c_uint]
    dll.DXStartPreview.restype = ctypes.c_uint
    dll.DXStartPreviewEx.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(Rect),
        ctypes.POINTER(Rect),
        ctypes.c_uint,
        ctypes.c_bool,
        ctypes.c_bool,
    ]
    dll.DXStartPreviewEx.restype = ctypes.c_uint
    dll.DXStopPreview.argtypes = [ctypes.c_void_p]
    dll.DXStopPreview.restype = ctypes.c_uint
    dll.DXSnapToJPGFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint, ctypes.POINTER(Rect)]
    dll.DXSnapToJPGFile.restype = ctypes.c_uint
    dll.DXGetFrameBuffer.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.c_uint,
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(Rect),
    ]
    dll.DXGetFrameBuffer.restype = ctypes.c_uint
    dll.DXGetBuf.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.c_bool,
    ]
    dll.DXGetBuf.restype = ctypes.c_uint
    dll.DXSaveJPGFile.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.c_uint,
    ]
    dll.DXSaveJPGFile.restype = ctypes.c_uint
    dll.DXStartRawVideoCallback.argtypes = [ctypes.c_void_p, RawVideoCallback, ctypes.c_void_p]
    dll.DXStartRawVideoCallback.restype = ctypes.c_uint
    dll.DXStopRawVideoCallback.argtypes = [ctypes.c_void_p]
    dll.DXStopRawVideoCallback.restype = ctypes.c_uint
    dll.DXStartCaptureEx.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(Rect),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint,
    ]
    dll.DXStartCaptureEx.restype = ctypes.c_uint
    dll.DXStopCapture.argtypes = [ctypes.c_void_p]
    dll.DXStopCapture.restype = ctypes.c_uint


def list_tags(dll: ctypes.CDLL, enum_func_name: str, limit: int = 32) -> Tuple[int, List[Dict[str, Any]]]:
    tags = (DeviceTag * limit)()
    count = ctypes.c_uint(limit)
    result = getattr(dll, enum_func_name)(tags, ctypes.byref(count))
    items = []
    if result == 0:
        for index in range(int(count.value)):
            items.append({"idx": int(tags[index].idx), "name": decode_name(bytes(tags[index].deviceName))})
    return int(result), items


def make_device_tag(idx: int, name: str) -> DeviceTag:
    tag = DeviceTag()
    tag.idx = idx
    tag.deviceName = name.encode("mbcs", errors="replace")[:127]
    return tag


def choose_codec(dll: ctypes.CDLL, handle: ctypes.c_void_p, requested: str) -> Dict[str, Any]:
    if not requested:
        return {"requested": requested, "selected": "raw", "result": 0}
    enum_result, codecs = list_tags(dll, "DXEnumVideoCodecs")
    selected_name = requested
    selected_idx = 2
    for codec in codecs:
        if str(codec["name"]).lower() == requested.lower():
            selected_name = str(codec["name"])
            selected_idx = int(codec["idx"])
            break
    else:
        for codec in codecs:
            if requested.lower() in str(codec["name"]).lower():
                selected_name = str(codec["name"])
                selected_idx = int(codec["idx"])
                break
    tag = make_device_tag(selected_idx, selected_name)
    result = int(dll.DXSetVideoCodec(handle, ctypes.byref(tag)))
    return {
        "requested": requested,
        "selected": selected_name,
        "selected_idx": selected_idx,
        "enum_result": format_code(enum_result),
        "available": codecs,
        "result": format_code(result),
        "ok": result == 0,
    }


def get_video_sources(dll: ctypes.CDLL, handle: ctypes.c_void_p) -> Dict[str, Any]:
    current = ctypes.c_uint(0)
    sources = (ctypes.c_uint * 16)()
    count = ctypes.c_ubyte(16)
    result = int(dll.DXGetVideoSources(handle, ctypes.byref(current), sources, ctypes.byref(count)))
    return {
        "result": format_code(result),
        "current": int(current.value),
        "sources": [int(sources[index]) for index in range(int(count.value))] if result == 0 else [],
        "count": int(count.value),
        "ok": result == 0,
    }


def get_signal_present(dll: ctypes.CDLL, handle: ctypes.c_void_p) -> Dict[str, Any]:
    signal = ctypes.c_uint(0)
    result = int(dll.DXGetSignalPresent(handle, ctypes.byref(signal)))
    return {"result": format_code(result), "signal": int(signal.value), "ok": result == 0}


def set_video_source(dll: ctypes.CDLL, handle: ctypes.c_void_p, source: Dict[str, Any]) -> Dict[str, Any]:
    method = source["method"]
    value = int(source["value"])
    if method == "current":
        return {"method": method, "value": None, "result": "skipped", "ok": True}
    if method == "legacy":
        result = int(dll.DXSetVideoSource(handle, value))
    elif method == "ex":
        result = int(dll.DXSetVideoSourceEx(handle, value))
    else:
        raise ValueError(f"unknown source method: {method}")
    return {"method": method, "value": value, "result": format_code(result), "ok": result == 0}


def check_file(path: Path, min_size: int = 512) -> Dict[str, Any]:
    exists = path.exists()
    size = path.stat().st_size if exists else 0
    header = path.read_bytes()[:16].hex() if exists and size else ""
    return {"path": str(path), "exists": exists, "size": size, "header_hex": header, "ok": exists and size >= min_size}


def save_jpg(
    dll: ctypes.CDLL,
    output: Path,
    buffer: Any,
    buffer_len: int,
    color_space: int,
    width: int,
    height: int,
    bytes_width: int,
) -> int:
    return int(
        dll.DXSaveJPGFile(
            str(output).encode("mbcs", errors="replace"),
            buffer,
            buffer_len,
            color_space,
            width,
            height,
            bytes_width,
            85,
        )
    )


def open_device(
    dll: ctypes.CDLL,
    args: argparse.Namespace,
    profile: Dict[str, Any],
    source: Dict[str, Any],
) -> Tuple[ctypes.c_void_p, Dict[str, Any]]:
    init_result = int(dll.DXInitialize())
    if init_result != 0:
        raise RuntimeError(f"DXInitialize failed: {format_code(init_result)}")
    count = int(dll.DXGetDeviceCount())
    if count <= args.device_index:
        raise RuntimeError(f"camera index {args.device_index} unavailable; count={count}")
    open_err = ctypes.c_uint(0)
    raw_handle = dll.DXOpenDevice(args.device_index, ctypes.byref(open_err))
    if not raw_handle or open_err.value != 0:
        raise RuntimeError(f"DXOpenDevice failed: {format_code(open_err.value)}")
    handle = ctypes.c_void_p(raw_handle)
    device_name = dll.DXGetDeviceName(handle)
    sources_before = get_video_sources(dll, handle)
    source_set = set_video_source(dll, handle, source)
    sources_after = get_video_sources(dll, handle)
    signal_before_run = get_signal_present(dll, handle)
    set_result = int(
        dll.DXSetVideoPara(
            handle,
            int(profile["standard"]),
            int(profile["colorspace"]),
            int(profile["width"]),
            int(profile["height"]),
            ctypes.c_float(float(profile["fps"])),
        )
    )
    if set_result != 0:
        raise RuntimeError(f"DXSetVideoPara failed: {format_code(set_result)}")
    codec = choose_codec(dll, handle, args.codec)
    return handle, {
        "device_count": count,
        "device_name": device_name.decode("mbcs", errors="replace") if device_name else "",
        "profile": profile,
        "source": source,
        "sources_before": sources_before,
        "source_set": source_set,
        "sources_after": sources_after,
        "signal_before_run": signal_before_run,
        "codec": codec,
    }


def close_device(dll: ctypes.CDLL, handle: Optional[ctypes.c_void_p]) -> None:
    if handle:
        try:
            dll.DXStopPreview(handle)
        except Exception:
            pass
        try:
            dll.DXStopCapture(handle)
        except Exception:
            pass
        try:
            dll.DXDeviceStop(handle)
        except Exception:
            pass
        try:
            dll.DXCloseDevice(handle)
        except Exception:
            pass
    try:
        dll.DXUninitialize()
    except Exception:
        pass


def run_device(dll: ctypes.CDLL, handle: ctypes.c_void_p, use_ex: bool) -> int:
    if use_ex:
        return int(dll.DXDeviceRunEx(handle, False, False))
    return int(dll.DXDeviceRun(handle))


def create_hidden_window(width: int, height: int) -> Optional[int]:
    user32 = ctypes.windll.user32
    user32.CreateWindowExW.argtypes = [
        ctypes.c_ulong,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    user32.CreateWindowExW.restype = ctypes.c_void_p
    hwnd = user32.CreateWindowExW(
        0,
        "STATIC",
        "MRC camera probe preview",
        0,
        0,
        0,
        int(width),
        int(height),
        None,
        None,
        None,
        None,
    )
    return int(hwnd) if hwnd else None


def destroy_window(hwnd: Optional[int]) -> None:
    if hwnd:
        ctypes.windll.user32.DestroyWindow(ctypes.c_void_p(hwnd))


def strategy_snap(dll: ctypes.CDLL, handle: ctypes.c_void_p, out_file: Path, profile: Dict[str, Any]) -> Dict[str, Any]:
    result = int(dll.DXSnapToJPGFile(handle, str(out_file).encode("mbcs", errors="replace"), 85, None))
    return {"result": format_code(result), "file": check_file(out_file), "ok": result == 0 and check_file(out_file)["ok"]}


def strategy_get_frame_buffer(
    dll: ctypes.CDLL,
    handle: ctypes.c_void_p,
    out_file: Path,
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    got_len = ctypes.c_uint(max(1, int(profile["width"]) * int(profile["height"]) * 4))
    color_space = ctypes.c_uint(int(profile["colorspace"]))
    width = ctypes.c_uint(int(profile["width"]))
    height = ctypes.c_uint(int(profile["height"]))
    bytes_width = ctypes.c_uint(int(profile["width"]) * 4)
    frame_buffer = (ctypes.c_ubyte * got_len.value)()
    result = int(
        dll.DXGetFrameBuffer(
            handle,
            frame_buffer,
            got_len.value,
            ctypes.byref(got_len),
            ctypes.byref(color_space),
            ctypes.byref(width),
            ctypes.byref(height),
            ctypes.byref(bytes_width),
            None,
        )
    )
    save_result = None
    if result == 0 and got_len.value > 0:
        save_result = save_jpg(
            dll,
            out_file,
            frame_buffer,
            int(got_len.value),
            int(color_space.value),
            int(width.value),
            int(height.value),
            int(bytes_width.value),
        )
    return {
        "result": format_code(result),
        "got_len": int(got_len.value),
        "color_space": int(color_space.value),
        "width": int(width.value),
        "height": int(height.value),
        "bytes_width": int(bytes_width.value),
        "save_result": format_code(save_result) if save_result is not None else None,
        "file": check_file(out_file),
        "ok": result == 0 and save_result == 0 and check_file(out_file)["ok"],
    }


def strategy_get_buf(dll: ctypes.CDLL, handle: ctypes.c_void_p, out_file: Path, profile: Dict[str, Any]) -> Dict[str, Any]:
    width = ctypes.c_uint(int(profile["width"]))
    height = ctypes.c_uint(int(profile["height"]))
    buffer_len = max(1, int(profile["width"]) * int(profile["height"]) * 4)
    frame_buffer = (ctypes.c_ubyte * buffer_len)()
    result = int(dll.DXGetBuf(handle, ctypes.byref(width), ctypes.byref(height), frame_buffer, False))
    save_result = None
    if result == 0 and width.value > 0 and height.value > 0:
        # DXGetBuf is documented as RGB data. Try RGB24 first; the oversized buffer is harmless.
        save_result = save_jpg(
            dll,
            out_file,
            frame_buffer,
            int(width.value) * int(height.value) * 3,
            CS_RGB24,
            int(width.value),
            int(height.value),
            int(width.value) * 3,
        )
    sample = bytes(frame_buffer[: min(len(frame_buffer), 6000)])
    return {
        "result": format_code(result),
        "width": int(width.value),
        "height": int(height.value),
        "sample_min": min(sample) if sample else None,
        "sample_max": max(sample) if sample else None,
        "sample_unique_count": len(set(sample)) if sample else 0,
        "save_result": format_code(save_result) if save_result is not None else None,
        "file": check_file(out_file),
        "ok": result == 0 and save_result == 0 and check_file(out_file)["ok"],
    }


def strategy_raw_callback(
    dll: ctypes.CDLL,
    handle: ctypes.c_void_p,
    out_file: Path,
    profile: Dict[str, Any],
    settle_seconds: float,
) -> Dict[str, Any]:
    event = threading.Event()
    frame: Dict[str, Any] = {}

    def on_frame(buffer: Any, color_space: int, width: int, height: int, bytes_width: int, context: Any) -> int:
        if not event.is_set() and buffer and width and height and bytes_width:
            buffer_len = int(height) * int(bytes_width)
            frame["bytes"] = ctypes.string_at(buffer, buffer_len)
            frame["buffer_len"] = buffer_len
            frame["color_space"] = int(color_space)
            frame["width"] = int(width)
            frame["height"] = int(height)
            frame["bytes_width"] = int(bytes_width)
            event.set()
        return 0

    callback = RawVideoCallback(on_frame)
    result = int(dll.DXStartRawVideoCallback(handle, callback, None))
    if result == 0:
        event.wait(settle_seconds)
        dll.DXStopRawVideoCallback(handle)
    save_result = None
    if frame:
        raw = frame["bytes"]
        frame_buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        save_result = save_jpg(
            dll,
            out_file,
            frame_buffer,
            int(frame["buffer_len"]),
            int(frame["color_space"]),
            int(frame["width"]),
            int(frame["height"]),
            int(frame["bytes_width"]),
        )
    return {
        "result": format_code(result),
        "frame": {key: value for key, value in frame.items() if key != "bytes"},
        "save_result": format_code(save_result) if save_result is not None else None,
        "file": check_file(out_file),
        "ok": result == 0 and save_result == 0 and check_file(out_file)["ok"],
    }


def strategy_preview_then_snap(
    dll: ctypes.CDLL,
    handle: ctypes.c_void_p,
    out_file: Path,
    profile: Dict[str, Any],
    mode: int,
    use_ex: bool,
    settle_seconds: float,
) -> Dict[str, Any]:
    hwnd = create_hidden_window(int(profile["width"]), int(profile["height"]))
    rect = Rect(0, 0, int(profile["width"]), int(profile["height"]))
    if use_ex:
        preview_result = int(dll.DXStartPreviewEx(handle, ctypes.c_void_p(hwnd), ctypes.byref(rect), None, mode, False, False))
    else:
        preview_result = int(dll.DXStartPreview(handle, ctypes.c_void_p(hwnd), ctypes.byref(rect), mode))
    time.sleep(settle_seconds)
    snap_result = None
    if preview_result == 0:
        snap_result = int(dll.DXSnapToJPGFile(handle, str(out_file).encode("mbcs", errors="replace"), 85, None))
        dll.DXStopPreview(handle)
    destroy_window(hwnd)
    return {
        "hwnd": hwnd,
        "preview_result": format_code(preview_result),
        "snap_result": format_code(snap_result) if snap_result is not None else None,
        "file": check_file(out_file),
        "ok": preview_result == 0 and snap_result == 0 and check_file(out_file)["ok"],
    }


def strategy_short_capture(
    dll: ctypes.CDLL,
    handle: ctypes.c_void_p,
    out_file: Path,
    file_format: int,
    seconds: float,
) -> Dict[str, Any]:
    result = int(dll.DXStartCaptureEx(handle, str(out_file).encode("mbcs", errors="replace"), 0, file_format, None, None, None, 1))
    if result == 0:
        time.sleep(seconds)
        stop_result = int(dll.DXStopCapture(handle))
    else:
        stop_result = None
    return {
        "start_result": format_code(result),
        "stop_result": format_code(stop_result) if stop_result is not None else None,
        "file": check_file(out_file, min_size=4096),
        "ok": result == 0 and stop_result == 0 and check_file(out_file, min_size=4096)["ok"],
    }


def profiles_from_args(args: argparse.Namespace) -> List[Dict[str, Any]]:
    if args.profile != "all":
        return [
            {
                "name": "custom",
                "width": args.width,
                "height": args.height,
                "fps": args.fps,
                "standard": args.standard,
                "colorspace": args.colorspace,
            }
        ]
    common = [
        ("ntsc_720_yuy2_30", 720, 480, 30.0, 1, CS_YUY2),
        ("ntsc_640_yuy2_30", 640, 480, 30.0, 1, CS_YUY2),
        ("ntsc_720_rgb24_30", 720, 480, 30.0, 1, CS_RGB24),
        ("ntsc_720_rgb32_30", 720, 480, 30.0, 1, CS_RGB32),
        ("pal_720_yuy2_25", 720, 576, 25.0, 32, CS_YUY2),
        ("vendor_win32_768_yuy2_25", 768, 576, 25.0, 32, CS_YUY2),
    ]
    return [
        {"name": name, "width": width, "height": height, "fps": fps, "standard": standard, "colorspace": colorspace}
        for name, width, height, fps, standard, colorspace in common
    ]


def sources_from_args(args: argparse.Namespace) -> List[Dict[str, Any]]:
    raw_sources = [item.strip() for item in args.sources.split(",") if item.strip()]
    methods = [item.strip() for item in args.source_methods.split(",") if item.strip()]
    sources: List[Dict[str, Any]] = []
    for raw_source in raw_sources:
        if raw_source.lower() == "current":
            sources.append({"name": "current", "method": "current", "value": None})
            continue
        value = int(raw_source)
        for method in methods:
            label = {1: "AV1", 2: "AV2", 3: "SVIDEO"}.get(value, str(value))
            sources.append({"name": f"{method}_{label}", "method": method, "value": value})
    return sources


def run_profile(
    dll: ctypes.CDLL,
    args: argparse.Namespace,
    profile: Dict[str, Any],
    source: Dict[str, Any],
    profile_dir: Path,
) -> Dict[str, Any]:
    profile_dir.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {"profile": profile, "source": source, "steps": {}, "ok": False}
    for run_name, use_ex in [("run_ex", True), ("run", False)]:
        handle = None
        try:
            handle, open_info = open_device(dll, args, profile, source)
            report["steps"][f"{run_name}_open"] = open_info
            run_result = run_device(dll, handle, use_ex)
            report["steps"][run_name] = {
                "result": format_code(run_result),
                "signal_after_run": get_signal_present(dll, handle),
            }
            time.sleep(args.settle_seconds)
            if run_result != 0:
                continue

            strategies = [
                ("snap", lambda path: strategy_snap(dll, handle, path, profile)),
                ("frame_buffer", lambda path: strategy_get_frame_buffer(dll, handle, path, profile)),
                ("get_buf", lambda path: strategy_get_buf(dll, handle, path, profile)),
                ("raw_callback", lambda path: strategy_raw_callback(dll, handle, path, profile, args.settle_seconds)),
                (
                    "preview_offscreen_snap",
                    lambda path: strategy_preview_then_snap(dll, handle, path, profile, DP_OFFSCREEN, False, args.settle_seconds),
                ),
                (
                    "preview_vmr9_snap",
                    lambda path: strategy_preview_then_snap(dll, handle, path, profile, DP_VMR9, False, args.settle_seconds),
                ),
                (
                    "preview_ex_d3d_snap",
                    lambda path: strategy_preview_then_snap(dll, handle, path, profile, DP_D3D, True, args.settle_seconds),
                ),
            ]
            for strategy_name, strategy in strategies:
                output = profile_dir / f"{run_name}_{strategy_name}.jpg"
                try:
                    result = strategy(output)
                except Exception as exc:  # noqa: BLE001
                    result = {"ok": False, "exception": repr(exc)}
                report["steps"][f"{run_name}_{strategy_name}"] = result
                if result.get("ok"):
                    report["ok"] = True
                    print(f"[OK] {profile['name']} {run_name}_{strategy_name}: {output}")
                    if args.stop_on_first:
                        return report

            for capture_name, file_format, suffix in [("capture_mp4", FILE_MP4, ".mp4"), ("capture_avi", FILE_AVI, ".avi")]:
                output = profile_dir / f"{run_name}_{capture_name}{suffix}"
                try:
                    result = strategy_short_capture(dll, handle, output, file_format, args.capture_seconds)
                except Exception as exc:  # noqa: BLE001
                    result = {"ok": False, "exception": repr(exc)}
                report["steps"][f"{run_name}_{capture_name}"] = result
                if result.get("ok"):
                    print(f"[OK] {profile['name']} {run_name}_{capture_name}: {output}")
        except Exception as exc:  # noqa: BLE001
            report["steps"][f"{run_name}_exception"] = repr(exc)
        finally:
            close_device(dll, handle)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe DXMediaCap camera preview/capture strategies.")
    parser.add_argument("--dll", default=os.getenv("MRC_DXMEDIA_DLL", ""), help="Path to DXMediaCap.dll.")
    parser.add_argument("--device-index", type=int, default=int(os.getenv("MRC_CAMERA_DEVICE_INDEX", "0")))
    parser.add_argument("--out", default=str(repo_root() / "camera_probe_output"))
    parser.add_argument("--profile", choices=["all", "custom"], default="all")
    parser.add_argument("--width", type=int, default=int(os.getenv("MRC_CAMERA_WIDTH", "720")))
    parser.add_argument("--height", type=int, default=int(os.getenv("MRC_CAMERA_HEIGHT", "480")))
    parser.add_argument("--fps", type=float, default=float(os.getenv("MRC_CAMERA_FPS", "30")))
    parser.add_argument("--standard", type=int, default=int(os.getenv("MRC_CAMERA_VIDEO_STANDARD", "1")))
    parser.add_argument("--colorspace", type=int, default=int(os.getenv("MRC_CAMERA_COLORSPACE", str(CS_YUY2))))
    parser.add_argument("--codec", default=os.getenv("MRC_CAMERA_VIDEO_CODEC", "x264 Codec"))
    parser.add_argument(
        "--sources",
        default=os.getenv("MRC_CAMERA_SOURCES", "0,1"),
        help="Comma-separated source values. VC demo uses DXSetVideoSourceEx with 0=AV1, 1=AV2, 2=SVIDEO. Use current to skip setting.",
    )
    parser.add_argument(
        "--source-methods",
        default=os.getenv("MRC_CAMERA_SOURCE_METHODS", "ex"),
        help="Comma-separated source set methods: legacy, ex.",
    )
    parser.add_argument("--settle-seconds", type=float, default=1.0)
    parser.add_argument("--capture-seconds", type=float, default=2.0)
    parser.add_argument("--stop-on-first", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_windows()
    root = repo_root()
    dll_path = Path(args.dll).resolve() if args.dll else default_dll_path(root).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "camera_probe_report.json"
    print(f"COM: {initialize_com()}")
    print(f"DLL: {dll_path}")
    print(f"Output: {out_dir}")
    dll = load_sdk(dll_path)
    init_result = int(dll.DXInitialize())
    if init_result != 0:
        raise RuntimeError(f"DXInitialize failed before enumeration: {format_code(init_result)}")
    device_count = int(dll.DXGetDeviceCount())
    device_enum_result, devices = list_tags(dll, "DXEnumVideoDevices")
    codec_enum_result, codecs = list_tags(dll, "DXEnumVideoCodecs")
    dll.DXUninitialize()
    report: Dict[str, Any] = {
        "python": sys.version,
        "python_bits": platform.architecture()[0],
        "dll": str(dll_path),
        "device_count": device_count,
        "devices": devices,
        "device_enum_result": format_code(device_enum_result),
        "codecs": codecs,
        "codec_enum_result": format_code(codec_enum_result),
        "profiles": [],
    }
    print(f"Devices: {devices}")
    print(f"Codecs: {codecs}")

    for profile in profiles_from_args(args):
        for source in sources_from_args(args):
            print(f"\n[PROFILE] {profile} [SOURCE] {source}")
            profile_dir = out_dir / f"{profile['name']}__{source['name']}"
            profile_report = run_profile(dll, args, profile, source, profile_dir)
            report["profiles"].append(profile_report)
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            if args.stop_on_first and profile_report.get("ok"):
                break
        if args.stop_on_first and report["profiles"] and report["profiles"][-1].get("ok"):
            break

    ok_files = []
    for profile_report in report["profiles"]:
        for step in profile_report.get("steps", {}).values():
            file_info = step.get("file") if isinstance(step, dict) else None
            if file_info and file_info.get("ok"):
                ok_files.append(file_info["path"])
    report["ok_files"] = ok_files
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport: {report_path}")
    print("Candidate files:")
    for path in ok_files:
        print(f"  {path}")
    if not ok_files:
        print("  none")
    return 0 if ok_files else 2


if __name__ == "__main__":
    raise SystemExit(main())

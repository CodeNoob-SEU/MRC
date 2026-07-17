from __future__ import annotations

from pathlib import Path
from dataclasses import asdict
import os
import platform
import sys
import threading
import time
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import AppConfig
from .events import EventBus
from .experiment import ExperimentCoordinator, ImageAdjustSettings


class StartExperimentRequest(BaseModel):
    output_root: Optional[str] = None
    window_minutes: Optional[float] = None
    camera_fps: Optional[float] = None
    threshold_volts: Optional[float] = None


class RecoverCameraRequest(BaseModel):
    camera_id: int = 1


class ImageAdjustRequest(BaseModel):
    target: str = "both"
    write_to_video: bool = False
    brightness: float = 1.0
    contrast: float = 1.0
    gamma: float = 1.0
    saturation: float = 1.0
    sharpness: float = 0.0


class StartManualRecordingRequest(BaseModel):
    output_root: Optional[str] = None
    camera_fps: Optional[float] = None


def create_app(config: Optional[AppConfig] = None, repo_root: Optional[Path] = None) -> FastAPI:
    config = config or AppConfig.from_env()
    repo_root = repo_root or Path(__file__).resolve().parents[2]
    event_bus = EventBus()
    coordinator = ExperimentCoordinator(config, repo_root, event_bus)

    app = FastAPI(title="MRC Integrated Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            # Packaged Electron loads the UI via file://, which sends
            # `Origin: null`; without this every API call fails CORS.
            "null",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.event_bus = event_bus
    app.state.coordinator = coordinator

    @app.on_event("startup")
    async def startup() -> None:
        event_bus.bind_loop()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        fast_default = "1" if platform.system() == "Windows" else "0"
        fast_shutdown = os.getenv("MRC_FAST_BACKEND_SHUTDOWN", fast_default).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if fast_shutdown:
            coordinator.close_fast_without_sdk_teardown()
            return
        timeout_seconds = float(os.getenv("MRC_SHUTDOWN_TIMEOUT_SECONDS", "4"))
        coordinator.close_with_deadline(timeout_seconds=timeout_seconds)

    @app.get("/health")
    def health() -> Dict[str, Any]:
        return {"ok": True, "status": coordinator.status_dict()}

    @app.get("/status")
    def status() -> Dict[str, Any]:
        return coordinator.status_dict()

    @app.get("/config")
    def get_config() -> Dict[str, Any]:
        output_root = Path(config.output_root)
        if not output_root.is_absolute():
            output_root = (repo_root / output_root).resolve()
        return {
            "output_root": str(output_root),
            "hardware_mode": config.hardware_mode,
            "camera2_enabled": config.camera2_enabled,
            "log_dir": os.getenv("MRC_LOG_DIR", str((repo_root / "logs").resolve())),
        }

    @app.get("/devices")
    def devices() -> Dict[str, Any]:
        return coordinator.devices()

    @app.get("/diagnostics/hardware")
    def diagnostics() -> Dict[str, Any]:
        return coordinator.diagnostics()

    @app.get("/diagnostics/runtime")
    def runtime_diagnostics() -> Dict[str, Any]:
        dxmedia_dll = (repo_root / config.camera.dxmedia_dll).resolve()
        dxmedia_dll2 = (repo_root / config.camera2.dxmedia_dll).resolve()
        usb3000_dll = (repo_root / config.daq.usb3000_dll).resolve()
        bundled_ffmpeg = (repo_root / "vendor" / "ffmpeg" / "windows" / "bin" / "ffmpeg.exe").resolve()
        return {
            "python_executable": sys.executable,
            "python_version": sys.version,
            "python_architecture": platform.architecture()[0],
            "machine": platform.machine(),
            "platform": platform.platform(),
            "cwd": os.getcwd(),
            "repo_root": str(repo_root),
            "hardware_mode": config.hardware_mode,
            "backend_host": config.host,
            "backend_port": config.port,
            "post_window_record_seconds": config.post_window_record_seconds,
            "video_trim_enabled": config.video_trim_enabled,
            "video_trim_mode": config.video_trim_mode,
            "ffmpeg_path": config.ffmpeg_path,
            "bundled_ffmpeg": str(bundled_ffmpeg),
            "bundled_ffmpeg_exists": bundled_ffmpeg.exists(),
            "camera_device_index": config.camera.device_index,
            "camera_width": config.camera.width,
            "camera_height": config.camera.height,
            "camera_fps": config.camera.fps,
            "camera_video_standard": config.camera.video_standard,
            "camera_colorspace": config.camera.colorspace,
            "camera_capture_format": config.camera.capture_format,
            "camera_video_codec": config.camera.video_codec,
            "camera_video_source_index": config.camera.video_source_index,
            "camera_preview_mode": config.camera.preview_mode,
            "camera_save_audio": config.camera.save_audio,
            "camera2_enabled": config.camera2_enabled,
            "camera2_device_index": config.camera2.device_index,
            "camera2_width": config.camera2.width,
            "camera2_height": config.camera2.height,
            "camera2_fps": config.camera2.fps,
            "camera2_video_standard": config.camera2.video_standard,
            "camera2_colorspace": config.camera2.colorspace,
            "camera2_capture_format": config.camera2.capture_format,
            "camera2_video_codec": config.camera2.video_codec,
            "camera2_video_source_index": config.camera2.video_source_index,
            "camera2_preview_mode": config.camera2.preview_mode,
            "camera2_save_audio": config.camera2.save_audio,
            "daq_device_index": config.daq.device_index,
            "vendor_arch": os.getenv("MRC_VENDOR_ARCH", "default-x64"),
            "dxmedia_dll": str(dxmedia_dll),
            "dxmedia_dll_exists": dxmedia_dll.exists(),
            "dxmedia_dll2": str(dxmedia_dll2),
            "dxmedia_dll2_exists": dxmedia_dll2.exists(),
            "usb3000_dll": str(usb3000_dll),
            "usb3000_dll_exists": usb3000_dll.exists(),
        }

    @app.post("/initialize")
    def initialize() -> Dict[str, Any]:
        try:
            return asdict(coordinator.initialize())
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/experiment/start")
    def start_experiment(request: StartExperimentRequest) -> Dict[str, Any]:
        try:
            return asdict(coordinator.start_experiment(
                output_root=request.output_root,
                window_minutes=request.window_minutes,
                camera_fps=request.camera_fps,
                threshold_volts=request.threshold_volts,
            ))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/experiment/stop")
    def stop_experiment() -> Dict[str, Any]:
        try:
            return asdict(coordinator.stop_experiment())
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/shutdown-fast")
    def shutdown_fast() -> Dict[str, Any]:
        def exit_soon() -> None:
            time.sleep(0.15)
            # Run cleanup on its own thread so os._exit is reached even if a
            # vendor DLL call inside cleanup blocks forever.
            cleanup = threading.Thread(
                target=coordinator.close_fast_without_sdk_teardown,
                name="mrc-fast-cleanup",
                daemon=True,
            )
            cleanup.start()
            cleanup.join(timeout=3.0)
            os._exit(0)

        threading.Thread(target=exit_soon, name="mrc-fast-shutdown", daemon=True).start()
        return {"ok": True, "mode": "fast_without_camera_sdk_teardown"}

    @app.post("/recover/camera")
    def recover_camera(request: RecoverCameraRequest) -> Dict[str, Any]:
        try:
            return coordinator.recover_camera(request.camera_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/image-adjust")
    def image_adjust(request: ImageAdjustRequest) -> Dict[str, Any]:
        try:
            return coordinator.set_image_adjust(
                target=request.target,
                write_to_video=request.write_to_video,
                settings=ImageAdjustSettings(
                    brightness=request.brightness,
                    contrast=request.contrast,
                    gamma=request.gamma,
                    saturation=request.saturation,
                    sharpness=request.sharpness,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/manual-recording/start")
    def start_manual_recording(request: StartManualRecordingRequest) -> Dict[str, Any]:
        try:
            return asdict(coordinator.start_manual_recording(
                output_root=request.output_root,
                camera_fps=request.camera_fps,
            ))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.websocket("/ws")
    async def websocket(websocket: WebSocket) -> None:
        await websocket.accept()
        queue = await event_bus.subscribe()
        try:
            await websocket.send_json({"type": "status", "payload": coordinator.status_dict()})
            while True:
                event = await queue.get()
                await websocket.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            event_bus.unsubscribe(queue)

    return app


app = create_app()

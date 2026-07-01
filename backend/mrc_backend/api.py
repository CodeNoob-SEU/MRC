from __future__ import annotations

from pathlib import Path
from dataclasses import asdict
import os
import platform
import sys
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import AppConfig
from .events import EventBus
from .experiment import ExperimentCoordinator


class StartExperimentRequest(BaseModel):
    output_root: str | None = None
    window_minutes: float | None = None
    camera_fps: float | None = None
    threshold_volts: float | None = None


def create_app(config: AppConfig | None = None, repo_root: Path | None = None) -> FastAPI:
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
        coordinator.close()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "status": coordinator.status_dict()}

    @app.get("/status")
    def status() -> dict[str, Any]:
        return coordinator.status_dict()

    @app.get("/devices")
    def devices() -> dict[str, Any]:
        return coordinator.devices()

    @app.get("/diagnostics/hardware")
    def diagnostics() -> dict[str, Any]:
        return coordinator.diagnostics()

    @app.get("/diagnostics/runtime")
    def runtime_diagnostics() -> dict[str, Any]:
        dxmedia_dll = (repo_root / config.camera.dxmedia_dll).resolve()
        usb3000_dll = (repo_root / config.daq.usb3000_dll).resolve()
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
            "camera_device_index": config.camera.device_index,
            "daq_device_index": config.daq.device_index,
            "vendor_arch": os.getenv("MRC_VENDOR_ARCH", "default-x64"),
            "dxmedia_dll": str(dxmedia_dll),
            "dxmedia_dll_exists": dxmedia_dll.exists(),
            "usb3000_dll": str(usb3000_dll),
            "usb3000_dll_exists": usb3000_dll.exists(),
        }

    @app.post("/initialize")
    def initialize() -> dict[str, Any]:
        try:
            return asdict(coordinator.initialize())
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/experiment/start")
    def start_experiment(request: StartExperimentRequest) -> dict[str, Any]:
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
    def stop_experiment() -> dict[str, Any]:
        try:
            return asdict(coordinator.stop_experiment())
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.websocket("/ws")
    async def websocket(websocket: WebSocket) -> None:
        await websocket.accept()
        queue = await event_bus.subscribe()
        await websocket.send_json({"type": "status", "payload": coordinator.status_dict()})
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            event_bus.unsubscribe(queue)

    return app


app = create_app()

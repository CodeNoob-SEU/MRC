from __future__ import annotations

import uvicorn

from .config import AppConfig
from .hardware.camera_process import sweep_stale_camera_workers


def main() -> None:
    config = AppConfig.from_env()
    try:
        sweep_stale_camera_workers()
    except Exception:  # noqa: BLE001
        pass
    uvicorn.run(
        "mrc_backend.api:app",
        host=config.host,
        port=config.port,
        reload=False,
        log_level="info",
        # Never wait forever on lingering connections (e.g. a websocket whose
        # client vanished) when the process is asked to stop.
        timeout_graceful_shutdown=5,
    )


if __name__ == "__main__":
    main()


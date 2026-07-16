from __future__ import annotations

import logging
import os
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn

from .config import AppConfig
from .hardware.camera_process import sweep_stale_camera_workers


def _setup_logging() -> None:
    """Console + rotating file logs so field issues can be diagnosed later."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_dir = Path(os.getenv("MRC_LOG_DIR", str(Path(__file__).resolve().parents[2] / "logs")))
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_dir / "mrc_backend.log",
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
        )
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )

    def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
        logging.getLogger("mrc_backend.threads").error(
            "Unhandled exception in thread %s",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _thread_excepthook


def main() -> None:
    _setup_logging()
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
        # Route uvicorn's logs through the root logging config above so they
        # land in the rotating file as well.
        log_config=None,
        # Never wait forever on lingering connections (e.g. a websocket whose
        # client vanished) when the process is asked to stop.
        timeout_graceful_shutdown=5,
    )


if __name__ == "__main__":
    main()

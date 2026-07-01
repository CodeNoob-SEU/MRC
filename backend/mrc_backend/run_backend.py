from __future__ import annotations

import uvicorn

from .config import AppConfig


def main() -> None:
    config = AppConfig.from_env()
    uvicorn.run(
        "mrc_backend.api:app",
        host=config.host,
        port=config.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()


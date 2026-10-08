from __future__ import annotations

import threading
import webbrowser

import uvicorn

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    browser_host = "127.0.0.1" if settings.host in {"0.0.0.0", "::"} else settings.host
    url = f"http://{browser_host}:{settings.port}"
    threading.Timer(1.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

LOGGER = logging.getLogger(__name__)


class DownloadError(RuntimeError):
    pass


def _validate_pexels_url(url: str) -> None:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (hostname == "pexels.com" or hostname.endswith(".pexels.com")):
        raise DownloadError("Từ chối tải URL không thuộc miền Pexels HTTPS.")


def download_file(url: str, destination: Path, timeout_seconds: int = 90, retries: int = 3) -> str:
    _validate_pexels_url(url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    last_error: Exception | None = None

    for attempt in range(max(1, retries)):
        digest = hashlib.sha256()
        try:
            with httpx.stream(
                "GET",
                url,
                timeout=httpx.Timeout(timeout_seconds, connect=20),
                follow_redirects=True,
                headers={"User-Agent": "StockScriptMatcher/1.0"},
            ) as response:
                response.raise_for_status()
                with temporary.open("wb") as output:
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        if chunk:
                            output.write(chunk)
                            digest.update(chunk)
            if temporary.stat().st_size == 0:
                raise DownloadError("File tải về có dung lượng 0 byte.")
            temporary.replace(destination)
            return digest.hexdigest()
        except (httpx.HTTPError, OSError, DownloadError) as exc:
            last_error = exc
            temporary.unlink(missing_ok=True)
            if attempt < retries - 1:
                time.sleep(1.0 * (2**attempt))

    raise DownloadError(f"Không tải được video: {last_error}")

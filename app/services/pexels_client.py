from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from app.models import Orientation, VideoCandidate

LOGGER = logging.getLogger(__name__)


class PexelsAPIError(RuntimeError):
    pass


class PexelsRateLimitError(PexelsAPIError):
    pass


class SQLiteResponseCache:
    def __init__(self, path: Path, ttl_hours: int) -> None:
        self.path = path
        self.ttl_seconds = ttl_hours * 3600
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS response_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_cache_created_at ON response_cache(created_at)")

    def get(self, cache_key: str) -> dict[str, Any] | None:
        threshold = time.time() - self.ttl_seconds
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload, created_at FROM response_cache WHERE cache_key = ?", (cache_key,)
            ).fetchone()
            if not row:
                return None
            if float(row[1]) < threshold:
                connection.execute("DELETE FROM response_cache WHERE cache_key = ?", (cache_key,))
                return None
            return json.loads(row[0])

    def set(self, cache_key: str, payload: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO response_cache(cache_key, payload, created_at) VALUES (?, ?, ?)",
                (cache_key, json.dumps(payload, ensure_ascii=False), time.time()),
            )


class PexelsClient:
    BASE_URL = "https://api.pexels.com/v1/videos/search"

    def __init__(
        self,
        api_key: str,
        cache_db: Path,
        cache_ttl_hours: int = 168,
        timeout_seconds: int = 30,
        max_retries: int = 4,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Thiếu Pexels API key.")
        self.api_key = api_key.strip()
        self.cache = SQLiteResponseCache(cache_db, cache_ttl_hours)
        self.max_retries = max(1, max_retries)
        self.client = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 15)),
            headers={"Authorization": self.api_key, "User-Agent": "StockScriptMatcher/1.0"},
            follow_redirects=True,
        )
        self.rate_limit: dict[str, str] = {}

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "PexelsClient":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    @staticmethod
    def _cache_key(params: dict[str, Any]) -> str:
        serialized = json.dumps(params, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def search_videos(
        self,
        query: str,
        orientation: Orientation,
        locale: str,
        per_page: int = 18,
        query_rank: int = 0,
        page: int = 1,
    ) -> list[VideoCandidate]:
        params: dict[str, Any] = {
            "query": query,
            "orientation": orientation,
            "size": "medium",
            "locale": locale,
            "per_page": max(1, min(per_page, 80)),
            "page": max(1, page),
        }
        cache_key = self._cache_key(params)
        payload = self.cache.get(cache_key)
        if payload is None:
            payload = self._request(params)
            self.cache.set(cache_key, payload)
        else:
            LOGGER.debug("Pexels cache hit for query=%s page=%d", query, page)

        videos = payload.get("videos") or []
        return [
            VideoCandidate.from_api(
                item,
                source_query=query,
                source_query_rank=query_rank,
                result_rank=result_rank,
            )
            for result_rank, item in enumerate(videos)
        ]

    def get_quota_info(self) -> dict[str, str]:
        if not self.rate_limit:
            try:
                self._request({"query": "nature", "per_page": 1, "page": 1})
            except Exception:
                pass
        return dict(self.rate_limit)


    def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.get(self.BASE_URL, params=params)
                self.rate_limit = {
                    key: value
                    for key in ("X-Ratelimit-Limit", "X-Ratelimit-Remaining", "X-Ratelimit-Reset")
                    if (value := response.headers.get(key)) is not None
                }
                if response.status_code == 401:
                    raise PexelsAPIError("Pexels API key không hợp lệ hoặc đã bị thu hồi.")
                if response.status_code == 429:
                    raise PexelsRateLimitError(
                        "Đã vượt giới hạn gọi Pexels API. Hãy đợi quota được làm mới hoặc giảm số truy vấn."
                    )
                if 400 <= response.status_code < 500:
                    detail = response.text[:300]
                    raise PexelsAPIError(f"Pexels API trả về lỗi {response.status_code}: {detail}")
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise PexelsAPIError("Pexels API trả về dữ liệu không đúng định dạng.")
                return data
            except PexelsRateLimitError:
                raise
            except PexelsAPIError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt >= self.max_retries - 1:
                    break
                time.sleep(min(8.0, 0.75 * (2**attempt)))

        raise PexelsAPIError(f"Không thể kết nối Pexels API sau {self.max_retries} lần thử: {last_error}")

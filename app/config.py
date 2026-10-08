from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    app_name: str = "Stock Script Matcher"
    host: str = "127.0.0.1"
    port: int = 8765
    pexels_api_key: str = ""
    max_upload_mb: int = 20
    max_segments: int = 300
    cache_ttl_hours: int = 168
    request_timeout_seconds: int = 30
    max_api_retries: int = 4
    default_results_per_query: int = 18
    default_max_queries_per_segment: int = 2
    job_workers: int = 2
    query_provider: str = "rules"

    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1])

    @property
    def runtime_dir(self) -> Path:
        path = self.project_root / "runtime"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def jobs_dir(self) -> Path:
        path = self.runtime_dir / "jobs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def cache_db(self) -> Path:
        path = self.runtime_dir / "cache" / "pexels_cache.sqlite3"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

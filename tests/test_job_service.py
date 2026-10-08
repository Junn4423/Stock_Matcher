from __future__ import annotations

import shutil
import time
import zipfile
from pathlib import Path

from app.config import Settings
from app.models import ProcessOptions, VideoCandidate, VideoFile
from app.services import job_service
from app.services.job_service import JobManager


class FakePexelsClient:
    def __init__(self, *args, **kwargs) -> None:
        self.rate_limit = {"X-Ratelimit-Limit": "20000", "X-Ratelimit-Remaining": "19999"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def search_videos(self, query, orientation, locale, per_page, query_rank):
        video_id = abs(hash(query)) % 100000 + 1
        file = VideoFile(
            id=video_id,
            quality="hd",
            file_type="video/mp4",
            width=1920,
            height=1080,
            fps=30,
            link="https://videos.pexels.com/sample.mp4",
        )
        return [
            VideoCandidate(
                id=video_id,
                width=1920,
                height=1080,
                url=f"https://www.pexels.com/video/{video_id}/",
                image="",
                duration=15,
                creator_name="Test Creator",
                creator_url="https://www.pexels.com",
                video_files=[file],
                source_query=query,
                source_query_rank=query_rank,
                result_rank=0,
            )
        ]


def test_job_manager_builds_result_zip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(job_service, "PexelsClient", FakePexelsClient)
    project_root = tmp_path / "project"
    (project_root / "runtime" / "jobs").mkdir(parents=True)
    settings = Settings(project_root=project_root, job_workers=1, max_segments=20)
    manager = JobManager(settings)

    upload = tmp_path / "input.txt"
    upload.write_text("AI hỗ trợ doanh nghiệp. Bác sĩ dùng dữ liệu để chăm sóc bệnh nhân.", encoding="utf-8")
    staged = tmp_path / "staged.txt"
    shutil.copy2(upload, staged)

    job_id = manager.create_job(staged, "input.txt", "fake-key", ProcessOptions())
    deadline = time.time() + 15
    job = None
    while time.time() < deadline:
        job = manager.get_job(job_id)
        if job and job["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    manager.executor.shutdown(wait=True)
    assert job is not None
    assert job["status"] == "completed", job.get("message")
    result_zip = Path(job["result_zip"])
    assert result_zip.exists()
    with zipfile.ZipFile(result_zip) as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert "timeline.csv" in names
    assert "subtitles.srt" in names
    assert any(name.endswith("_stock_plan.docx") for name in names)
    assert any(name.startswith("audio/") for name in names)


def test_job_manager_with_tts_and_rough_cut(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(job_service, "PexelsClient", FakePexelsClient)
    from app.services.tts_service import create_silent_audio
    monkeypatch.setattr(job_service, "generate_tts_audio", lambda text, path, voice: create_silent_audio(path, 2.5))

    project_root = tmp_path / "project"
    (project_root / "runtime" / "jobs").mkdir(parents=True)
    settings = Settings(project_root=project_root, job_workers=1, max_segments=20)
    manager = JobManager(settings)

    upload = tmp_path / "input.txt"
    upload.write_text("Chào mừng bạn đến với thử nghiệm hệ thống tạo video tự động.", encoding="utf-8")
    staged = tmp_path / "staged.txt"
    shutil.copy2(upload, staged)

    options = ProcessOptions(
        enable_tts=True,
        download_videos=True,
        build_rough_cut=True,
        transition_duration=0.4,
    )
    job_id = manager.create_job(staged, "input.txt", "fake-key", options)
    deadline = time.time() + 30
    job = None
    while time.time() < deadline:
        job = manager.get_job(job_id)
        if job and job["status"] in {"completed", "failed"}:
            break
        time.sleep(0.1)


    manager.executor.shutdown(wait=True)
    assert job is not None
    assert job["status"] == "completed", job.get("message")
    result_zip = Path(job["result_zip"])
    assert result_zip.exists()
    with zipfile.ZipFile(result_zip) as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert any(name.startswith("audio/") for name in names)


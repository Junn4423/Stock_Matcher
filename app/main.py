from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.models import ProcessOptions
from app.services.job_service import JobManager
from app.services.text_extractor import SUPPORTED_EXTENSIONS

settings = get_settings()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, version="1.0.0")
app.mount("/static", StaticFiles(directory=settings.project_root / "app" / "static"), name="static")
job_manager = JobManager(settings)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html_path = settings.project_root / "app" / "templates" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/api/pexels/quota")
def check_pexels_quota(api_key: str = "") -> JSONResponse:
    effective_key = api_key.strip() or settings.pexels_api_key.strip()
    if not effective_key:
        return JSONResponse({"configured": False, "message": "Chưa nhập API key"}, status_code=200)
    try:
        from app.services.pexels_client import PexelsClient
        with PexelsClient(
            api_key=effective_key,
            cache_db=settings.cache_db,
            cache_ttl_hours=settings.cache_ttl_hours,
            timeout_seconds=settings.request_timeout_seconds,
            max_retries=1,
        ) as client:
            quota_info = client.get_quota_info()
            return JSONResponse(
                {
                    "configured": True,
                    "limit": quota_info.get("X-Ratelimit-Limit", "200"),
                    "remaining": quota_info.get("X-Ratelimit-Remaining", "200"),
                    "reset": quota_info.get("X-Ratelimit-Reset", ""),
                }
            )
    except Exception as exc:
        return JSONResponse({"configured": True, "error": str(exc)}, status_code=400)


@app.get("/api/tts/voices")
def get_tts_voices() -> JSONResponse:
    from app.services.tts_service import get_voice_catalog
    return JSONResponse({"voices": get_voice_catalog()})



@app.post("/api/jobs")

async def create_job(
    file: UploadFile = File(...),
    api_key: str = Form(default=""),
    segment_mode: str = Form(default="smart"),
    orientation: str = Form(default="landscape"),
    min_segment_words: int = Form(default=7),
    max_segment_words: int = Form(default=34),
    words_per_minute: int = Form(default=150),
    max_queries_per_segment: int = Form(default=2),
    results_per_query: int = Form(default=18),
    download_videos: bool = Form(default=False),
    build_rough_cut: bool = Form(default=False),
    enable_tts: bool = Form(default=True),
    tts_voice: str = Form(default="auto"),
    transition_duration: float = Form(default=0.4),
) -> JSONResponse:
    original_name = Path(file.filename or "transcript.txt").name
    extension = Path(original_name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Định dạng không hỗ trợ. Hỗ trợ: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )
    if not (api_key.strip() or settings.pexels_api_key.strip()):
        raise HTTPException(status_code=400, detail="Hãy nhập Pexels API key hoặc cấu hình trong file .env.")
    if segment_mode not in {"smart", "sentence", "paragraph"}:
        raise HTTPException(status_code=400, detail="segment_mode không hợp lệ.")
    if orientation not in {"landscape", "portrait", "square"}:
        raise HTTPException(status_code=400, detail="orientation không hợp lệ.")
    if not 3 <= min_segment_words <= 30:
        raise HTTPException(status_code=400, detail="min_segment_words phải trong khoảng 3–30.")
    if not min_segment_words <= max_segment_words <= 100:
        raise HTTPException(status_code=400, detail="max_segment_words phải lớn hơn min và không quá 100.")
    if not 60 <= words_per_minute <= 260:
        raise HTTPException(status_code=400, detail="words_per_minute phải trong khoảng 60–260.")
    if not 1 <= max_queries_per_segment <= 4:
        raise HTTPException(status_code=400, detail="max_queries_per_segment phải trong khoảng 1–4.")
    if not 5 <= results_per_query <= 40:
        raise HTTPException(status_code=400, detail="results_per_query phải trong khoảng 5–40.")
    if not 0.0 <= transition_duration <= 2.0:
        raise HTTPException(status_code=400, detail="transition_duration phải từ 0 đến 2.0 giây.")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    raw = await file.read(max_bytes + 1)
    await file.close()
    if len(raw) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File vượt quá {settings.max_upload_mb} MB.")
    if not raw:
        raise HTTPException(status_code=400, detail="File rỗng.")

    options = ProcessOptions(
        segment_mode=segment_mode,  # type: ignore[arg-type]
        orientation=orientation,  # type: ignore[arg-type]
        min_segment_words=min_segment_words,
        max_segment_words=max_segment_words,
        words_per_minute=words_per_minute,
        max_queries_per_segment=max_queries_per_segment,
        results_per_query=results_per_query,
        download_videos=download_videos or build_rough_cut,
        build_rough_cut=build_rough_cut,
        enable_tts=enable_tts,
        tts_voice=tts_voice,
        transition_duration=transition_duration,
    )


    with tempfile.NamedTemporaryFile(
        prefix="stock_upload_", suffix=extension, dir=settings.runtime_dir, delete=False
    ) as temporary:
        temporary.write(raw)
        temporary_path = Path(temporary.name)

    try:
        job_id = job_manager.create_job(temporary_path, original_name, api_key, options)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return JSONResponse({"job_id": job_id, "status_url": f"/api/jobs/{job_id}"}, status_code=202)


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, object]:
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy job.")
    public_job = {
        key: value
        for key, value in job.items()
        if key not in {"input_path", "job_dir", "result_zip"}
    }
    if job.get("status") == "completed":
        public_job["download_url"] = f"/api/jobs/{job_id}/download"
    return public_job


@app.get("/api/jobs/{job_id}/download")
def download_result(job_id: str) -> FileResponse:
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy job.")
    if job.get("status") != "completed" or not job.get("result_zip"):
        raise HTTPException(status_code=409, detail="Job chưa hoàn tất.")
    result_path = Path(str(job["result_zip"])).resolve()
    expected_root = (settings.jobs_dir / job_id).resolve()
    if expected_root not in result_path.parents or not result_path.exists():
        raise HTTPException(status_code=404, detail="File kết quả không còn tồn tại.")
    return FileResponse(result_path, media_type="application/zip", filename=result_path.name)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception) -> JSONResponse:
    LOGGER.exception("Unhandled application error")
    return JSONResponse(status_code=500, content={"detail": f"Lỗi nội bộ: {exc}"})

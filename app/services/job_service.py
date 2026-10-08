from __future__ import annotations

import csv
import json
import logging
import re
import shutil
import threading
import uuid
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings
from app.models import MatchResult, ProcessOptions
from app.services.composer import ComposeError, build_rough_cut
from app.services.docx_exporter import export_docx
from app.services.downloader import DownloadError, download_file
from app.services.pexels_client import PexelsAPIError, PexelsClient, PexelsRateLimitError
from app.services.query_engine import VisualQueryEngine
from app.services.ranker import rank_candidates
from app.services.segmenter import segment_text
from app.services.text_extractor import extract_text
from app.services.tts_service import generate_tts_audio

LOGGER = logging.getLogger(__name__)
_VI_SIGNAL = re.compile(r"[ăâđêôơưàáạảãằắặẳẵầấậẩẫèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ]", re.I)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_stem(name: str) -> str:
    stem = Path(name).stem
    cleaned = re.sub(r"[^A-Za-z0-9À-ỹ._-]+", "_", stem).strip("._")
    return cleaned[:80] or "transcript"


def _format_srt_time(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _query_locale(query: str) -> str:
    return "vi-VN" if _VI_SIGNAL.search(query) else "en-US"


class JobManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.executor = ThreadPoolExecutor(max_workers=settings.job_workers, thread_name_prefix="stock-job")
        self.jobs: dict[str, dict[str, Any]] = {}
        self.lock = threading.RLock()

    def create_job(
        self,
        upload_path: Path,
        original_name: str,
        api_key: str,
        options: ProcessOptions,
    ) -> str:
        job_id = uuid.uuid4().hex
        job_dir = self.settings.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        target_upload = job_dir / f"input{upload_path.suffix.lower()}"
        try:
            shutil.move(str(upload_path), target_upload)
        except Exception:
            shutil.copy2(str(upload_path), target_upload)
            try:
                upload_path.unlink(missing_ok=True)
            except Exception:
                pass


        job = {
            "id": job_id,
            "status": "queued",
            "progress": 0,
            "message": "Đang chờ xử lý",
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "original_name": original_name,
            "input_path": str(target_upload),
            "job_dir": str(job_dir),
            "options": options.to_dict(),
            "warnings": [],
            "result_zip": "",
            "rate_limit": {},
        }
        with self.lock:
            self.jobs[job_id] = job
            self._persist(job)
        self.executor.submit(self._run_job, job_id, api_key)
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job:
                return dict(job)
        job_file = self.settings.jobs_dir / job_id / "job.json"
        if job_file.exists():
            try:
                return json.loads(job_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
        return None

    def _persist(self, job: dict[str, Any]) -> None:
        path = Path(job["job_dir"]) / "job.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _update(self, job_id: str, **changes: Any) -> None:
        with self.lock:
            job = self.jobs[job_id]
            job.update(changes)
            job["updated_at"] = _utc_now()
            self._persist(job)

    def _warn(self, job_id: str, warning: str) -> None:
        with self.lock:
            job = self.jobs[job_id]
            job.setdefault("warnings", []).append(warning)
            job["updated_at"] = _utc_now()
            self._persist(job)

    def _log(self, job_id: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        LOGGER.info("Job %s | %s", job_id[:8], message)
        with self.lock:
            job = self.jobs.get(job_id)
            if job:
                logs = job.setdefault("log_history", [])
                logs.append(log_line)
                if len(logs) > 120:
                    job["log_history"] = logs[-120:]
                job["updated_at"] = _utc_now()
                self._persist(job)

    def _run_job(self, job_id: str, api_key: str) -> None:
        job = self.jobs[job_id]
        job_dir = Path(job["job_dir"])
        input_path = Path(job["input_path"])
        options = ProcessOptions(**job["options"])
        effective_key = api_key.strip() or self.settings.pexels_api_key.strip()

        try:
            self._log(job_id, "Bắt đầu đọc transcript và phân đoạn nội dung")
            self._update(job_id, status="running", progress=3, message="Đang đọc transcript")
            text = extract_text(input_path)

            self._update(job_id, progress=5, message="Đang phân đoạn nội dung")
            segments = segment_text(text, options)
            if not segments:
                raise ValueError("Transcript không tạo được phân đoạn hợp lệ.")
            if len(segments) > self.settings.max_segments:
                raise ValueError(
                    f"Transcript tạo ra {len(segments)} phân đoạn, vượt giới hạn {self.settings.max_segments}. "
                    "Hãy tăng độ dài mỗi đoạn hoặc chỉnh MAX_SEGMENTS trong .env."
                )

            self._log(job_id, f"Đã phân đoạn thành công {len(segments)} phân đoạn kịch bản")

            query_engine = VisualQueryEngine(text)
            used_video_ids: set[int] = set()
            creator_usage: Counter[str] = Counter()
            matches: list[MatchResult] = []
            rate_limited = False

            with PexelsClient(
                api_key=effective_key,
                cache_db=self.settings.cache_db,
                cache_ttl_hours=self.settings.cache_ttl_hours,
                timeout_seconds=self.settings.request_timeout_seconds,
                max_retries=self.settings.max_api_retries,
            ) as pexels:
                for offset, segment in enumerate(segments):
                    plan = query_engine.build_plan(segment)
                    candidates_by_id: dict[int, Any] = {}
                    queries = plan.all_queries[: options.max_queries_per_segment]

                    if not rate_limited:
                        for query_rank, query in enumerate(queries):
                            try:
                                found = pexels.search_videos(
                                    query=query,
                                    orientation=options.orientation,
                                    locale=_query_locale(query),
                                    per_page=options.results_per_query,
                                    query_rank=query_rank,
                                )
                            except PexelsRateLimitError as exc:
                                rate_limited = True
                                self._warn(job_id, str(exc) + " Report sẽ giữ các kết quả đã tìm được.")
                                break
                            for candidate in found:
                                existing = candidates_by_id.get(candidate.id)
                                if existing is None or candidate.source_query_rank < existing.source_query_rank:
                                    candidates_by_id[candidate.id] = candidate
                            if len(candidates_by_id) >= 8:
                                break

                        # Nếu các candidate trả về đều đã dùng trước đó, tự động tìm thêm page 2 để chống trùng
                        has_unused = any(cid not in used_video_ids for cid in candidates_by_id)
                        if not has_unused and not rate_limited:
                            try:
                                found_p2 = pexels.search_videos(
                                    query=plan.primary_query,
                                    orientation=options.orientation,
                                    locale=_query_locale(plan.primary_query),
                                    per_page=options.results_per_query,
                                    query_rank=0,
                                    page=2,
                                )
                                for candidate in found_p2:
                                    if candidate.id not in candidates_by_id:
                                        candidates_by_id[candidate.id] = candidate
                            except Exception:
                                pass

                    match = rank_candidates(
                        segment=segment,
                        query_plan=plan,
                        candidates=list(candidates_by_id.values()),
                        orientation=options.orientation,
                        used_video_ids=used_video_ids,
                        creator_usage=creator_usage,
                    )
                    if match.video:
                        used_video_ids.add(match.video.id)
                        creator_usage[match.video.creator_name] += 1
                    matches.append(match)

                    progress = 5 + int(((offset + 1) / len(segments)) * 35)
                    self._log(
                        job_id,
                        f"[Tìm video {offset + 1}/{len(segments)}] "
                        f"Phân đoạn {segment.index}: Picked #{match.video.id if match.video else 'N/A'} (Score: {match.score:.2f})",
                    )
                    self._update(
                        job_id,
                        progress=progress,
                        message=f"Đã tìm video cho {offset + 1}/{len(segments)} phân đoạn",
                        rate_limit=pexels.rate_limit,
                    )

            if options.download_videos:
                videos_dir = job_dir / "videos"
                for offset, match in enumerate(matches):
                    if match.selected_file is None or match.video is None:
                        continue
                    destination = videos_dir / f"{match.segment.index:04d}_pexels_{match.video.id}.mp4"
                    try:
                        download_file(match.selected_file.link, destination)
                        match.local_video_path = str(destination)
                    except DownloadError as exc:
                        self._warn(job_id, f"Đoạn {match.segment.index}: {exc}")
                    progress = 40 + int(((offset + 1) / len(matches)) * 20)
                    self._log(job_id, f"[Tải video {offset + 1}/{len(matches)}] Pexels #{match.video.id}")
                    self._update(
                        job_id,
                        progress=progress,
                        message=f"Đang tải video {offset + 1}/{len(matches)}",
                    )

            audio_paths: dict[int, Path] = {}
            if options.enable_tts:
                audio_dir = job_dir / "audio"
                total_seg = len(segments)
                for offset, segment in enumerate(segments):
                    audio_file = audio_dir / f"{segment.index:04d}_voice.mp3"
                    try:
                        dur = generate_tts_audio(segment.text, audio_file, options.tts_voice)
                        segment.estimated_seconds = max(dur, 2.5)
                        audio_paths[segment.index] = audio_file
                        self._log(
                            job_id,
                            f"[TTS {offset + 1}/{total_seg}] Giọng '{options.tts_voice}' ({dur:.2f}s) - {segment.text[:30]}...",
                        )
                    except Exception as exc:
                        self._warn(job_id, f"Đoạn {segment.index}: Không thể tạo giọng đọc TTS: {exc}")

                    progress = 60 + int(((offset + 1) / total_seg) * 20)
                    self._update(
                        job_id,
                        progress=progress,
                        message=f"Đang tạo giọng đọc TTS ({offset + 1}/{total_seg})",
                    )

            self._update(job_id, progress=82, message="Đang tạo DOCX và manifest")
            stem = _safe_stem(job["original_name"])
            docx_path = job_dir / f"{stem}_stock_plan.docx"
            export_docx(matches, options, job["original_name"], docx_path)
            self._write_manifest(job_dir, matches, options, job["original_name"])

            if options.build_rough_cut:
                self._log(job_id, "Bắt đầu cắt video clips, áp dụng fade transition & ghép voiceover")
                self._update(job_id, progress=85, message="Đang cắt video & chuyển cảnh tự động")

                def _compose_progress(idx: int, total: int, step_desc: str) -> None:
                    prog = 85 + int(((idx + 1) / total) * 12)
                    self._log(job_id, f"[Cut & Transition {idx + 1}/{total}] {step_desc}")
                    self._update(job_id, progress=prog, message=f"Đang ghép video clip ({idx + 1}/{total})")

                try:
                    build_rough_cut(
                        matches,
                        job_dir,
                        options.orientation,
                        options.transition_duration,
                        audio_paths,
                        progress_callback=_compose_progress,
                    )
                    self._log(job_id, "Ghép video rough_cut.mp4 hoàn tất")
                except ComposeError as exc:
                    self._warn(job_id, f"Không dựng được rough-cut: {exc}")

            self._log(job_id, "Đang đóng gói ZIP toàn bộ kết quả")
            self._update(job_id, progress=97, message="Đang đóng gói kết quả")
            zip_path = self._zip_result(job_dir, stem)
            self._log(job_id, f"Hoàn tất! File kết quả: {zip_path.name}")
            self._update(
                job_id,
                status="completed",
                progress=100,
                message="Hoàn tất",
                result_zip=str(zip_path),
                segment_count=len(matches),
                matched_count=sum(1 for match in matches if match.video is not None),
                downloaded_count=sum(1 for match in matches if match.local_video_path),
            )

        except Exception as exc:
            LOGGER.exception("Job %s failed", job_id)
            self._update(job_id, status="failed", message=str(exc), progress=100)

    @staticmethod
    def _write_manifest(
        job_dir: Path,
        matches: list[MatchResult],
        options: ProcessOptions,
        source_name: str,
    ) -> None:
        serialized_segments: list[dict[str, Any]] = []
        for match in matches:
            item = match.to_dict()
            if match.local_video_path:
                try:
                    item["local_video_path"] = Path(match.local_video_path).relative_to(job_dir).as_posix()
                except ValueError:
                    item["local_video_path"] = Path(match.local_video_path).name
            serialized_segments.append(item)
        manifest = {
            "source": source_name,
            "generated_at": _utc_now(),
            "options": options.to_dict(),
            "segments": serialized_segments,
        }
        (job_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        with (job_dir / "timeline.csv").open("w", newline="", encoding="utf-8-sig") as output:
            writer = csv.writer(output)
            writer.writerow(
                [
                    "index", "script", "estimated_seconds", "search_query", "pexels_url",
                    "direct_mp4", "creator", "resolution", "score", "local_file",
                ]
            )
            for match in matches:
                writer.writerow(
                    [
                        match.segment.index,
                        match.segment.text,
                        match.segment.estimated_seconds,
                        match.query_plan.primary_query,
                        match.video.url if match.video else "",
                        match.selected_file.link if match.selected_file else "",
                        match.video.creator_name if match.video else "",
                        (
                            f"{match.selected_file.width}x{match.selected_file.height}"
                            if match.selected_file
                            else ""
                        ),
                        round(match.score, 4),
                        Path(match.local_video_path).name if match.local_video_path else "",
                    ]
                )

        current = 0.0
        srt_lines: list[str] = []
        for match in matches:
            end = current + match.segment.estimated_seconds
            srt_lines.extend(
                [
                    str(match.segment.index),
                    f"{_format_srt_time(current)} --> {_format_srt_time(end)}",
                    match.segment.text,
                    "",
                ]
            )
            current = end
        (job_dir / "subtitles.srt").write_text("\n".join(srt_lines), encoding="utf-8-sig")

    @staticmethod
    def _zip_result(job_dir: Path, stem: str) -> Path:
        zip_path = job_dir / f"{stem}_stock_matcher_result.zip"
        excluded = {"job.json", zip_path.name}
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(job_dir.rglob("*")):
                if (
                    not path.is_file()
                    or path.name in excluded
                    or path.name.startswith("input.")
                    or "compose_work" in path.parts
                ):
                    continue
                archive.write(path, path.relative_to(job_dir))
        return zip_path

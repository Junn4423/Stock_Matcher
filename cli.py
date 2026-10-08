from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

from app.config import get_settings
from app.models import ProcessOptions
from app.services.job_service import JobManager

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Match transcript segments with Pexels stock videos.")
    parser.add_argument("input", type=Path, help="DOCX/TXT/MD/PDF/SRT/VTT transcript")
    parser.add_argument("--api-key", default="", help="Pexels API key; ưu tiên hơn .env")
    parser.add_argument("--orientation", choices=["landscape", "portrait", "square"], default="landscape")
    parser.add_argument("--mode", choices=["smart", "sentence", "paragraph"], default="smart")
    parser.add_argument("--min-words", type=int, default=7)
    parser.add_argument("--max-words", type=int, default=34)
    parser.add_argument("--wpm", type=int, default=150)
    parser.add_argument("--queries", type=int, default=2)
    parser.add_argument("--results", type=int, default=18)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--compose", action="store_true", help="Tải video và dựng rough_cut.mp4")
    parser.add_argument("--no-tts", action="store_true", help="Tắt tự động đọc voiceover")
    parser.add_argument("--voice", default="auto", help="Mã voice TTS (ví dụ: vi-VN-HoaiMyNeural)")
    parser.add_argument("--transition", type=float, default=0.4, help="Thời lượng chuyển cảnh fade in/out (giây)")
    parser.add_argument("--output", type=Path, default=Path.cwd(), help="Thư mục nhận ZIP kết quả")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    source = args.input.resolve()
    if not source.exists() or not source.is_file():
        print(f"Không tìm thấy file: {source}", file=sys.stderr)
        return 2

    options = ProcessOptions(
        segment_mode=args.mode,
        orientation=args.orientation,
        min_segment_words=args.min_words,
        max_segment_words=args.max_words,
        words_per_minute=args.wpm,
        max_queries_per_segment=args.queries,
        results_per_query=args.results,
        download_videos=args.download or args.compose,
        build_rough_cut=args.compose,
        enable_tts=not args.no_tts,
        tts_voice=args.voice,
        transition_duration=args.transition,
    )


    fd, temp_str = tempfile.mkstemp(prefix="stock_cli_", suffix=source.suffix, dir=settings.runtime_dir)
    import os
    os.close(fd)
    temporary = Path(temp_str)
    shutil.copy2(source, temporary)
    manager = JobManager(settings)
    try:
        job_id = manager.create_job(temporary, source.name, args.api_key, options)
        last_message = ""
        while True:
            job = manager.get_job(job_id)
            if not job:
                print("Mất trạng thái job.", file=sys.stderr)
                return 3
            message = f"[{job.get('progress', 0):3}%] {job.get('message', '')}"
            if message != last_message:
                print(message)
                last_message = message
            if job.get("status") == "completed":
                result = Path(str(job["result_zip"]))
                args.output.mkdir(parents=True, exist_ok=True)
                destination = args.output / result.name
                shutil.copy2(result, destination)
                print(f"Hoàn tất: {destination}")
                return 0
            if job.get("status") == "failed":
                print(f"Thất bại: {job.get('message')}", file=sys.stderr)
                return 4
            time.sleep(0.7)
    finally:
        manager.executor.shutdown(wait=False, cancel_futures=False)


if __name__ == "__main__":
    raise SystemExit(main())

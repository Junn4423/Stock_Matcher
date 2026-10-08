from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg

from app.models import MatchResult, Orientation

LOGGER = logging.getLogger(__name__)


class ComposeError(RuntimeError):
    pass


def _ffmpeg_executable() -> str:
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - phụ thuộc nền tảng
        raise ComposeError(f"Không tìm thấy FFmpeg: {exc}") from exc


def _run(command: list[str]) -> None:
    LOGGER.debug("Running FFmpeg command: %s", command)
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise ComposeError(completed.stderr[-2000:])


from typing import Callable

def build_rough_cut(
    matches: list[MatchResult],
    job_dir: Path,
    orientation: Orientation,
    transition_duration: float = 0.4,
    audio_paths: dict[int, Path] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> Path:
    ffmpeg = _ffmpeg_executable()
    work_dir = job_dir / "compose_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    normalized_files: list[Path] = []
    normalized_audio_files: list[Path] = []
    audio_paths = audio_paths or {}

    width, height = {
        "landscape": (1920, 1080),
        "portrait": (1080, 1920),
        "square": (1080, 1080),
    }[orientation]

    total_matches = len(matches)
    for idx, match in enumerate(matches):
        if progress_callback:
            progress_callback(idx, total_matches, f"Đang xử lý phân đoạn {match.segment.index}/{total_matches}")

        if not match.local_video_path:
            continue
        source = Path(match.local_video_path)
        if not source.exists():
            continue
        output = work_dir / f"segment_{match.segment.index:04d}.mp4"
        duration = max(2.5, match.segment.estimated_seconds)
        
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps=30,format=yuv420p"
        )
        trans_dur = min(transition_duration, duration / 3)
        if trans_dur > 0:
            vf += f",fade=t=in:st=0:d={trans_dur:.3f},fade=t=out:st={duration - trans_dur:.3f}:d={trans_dur:.3f}"

        _run(
            [
                ffmpeg,
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(source),
                "-t",
                f"{duration:.3f}",
                "-an",
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
        normalized_files.append(output)

        audio_source = audio_paths.get(match.segment.index)
        if audio_source and audio_source.exists():
            if audio_source.stat().st_size < 512:
                from app.services.tts_service import create_silent_audio
                create_silent_audio(audio_source, duration=duration)

            audio_out = work_dir / f"segment_{match.segment.index:04d}_audio.aac"
            try:
                _run(
                    [
                        ffmpeg,
                        "-y",
                        "-i",
                        str(audio_source),
                        "-af",
                        f"apad=whole_dur={duration:.3f}",
                        "-t",
                        f"{duration:.3f}",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "192k",
                        str(audio_out),
                    ]
                )
            except Exception as exc:
                LOGGER.warning("FFmpeg audio decode failed for segment %d: %s. Re-generating silent audio fallback.", match.segment.index, exc)
                from app.services.tts_service import create_silent_audio
                create_silent_audio(audio_source, duration=duration)
                _run(
                    [
                        ffmpeg,
                        "-y",
                        "-i",
                        str(audio_source),
                        "-af",
                        f"apad=whole_dur={duration:.3f}",
                        "-t",
                        f"{duration:.3f}",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "192k",
                        str(audio_out),
                    ]
                )
            normalized_audio_files.append(audio_out)


    if not normalized_files:
        raise ComposeError("Không có video đã tải để ghép rough-cut.")

    concat_lines = []
    for path in normalized_files:
        escaped_path = path.as_posix().replace("'", "'\\''")
        concat_lines.append(f"file '{escaped_path}'")

    concat_file = work_dir / "concat.txt"
    concat_file.write_text("\n".join(concat_lines), encoding="utf-8")
    
    master_video = work_dir / "master_video.mp4"
    _run(
        [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(master_video),
        ]
    )

    final_path = job_dir / "rough_cut.mp4"

    if len(normalized_audio_files) == len(normalized_files):
        audio_concat_lines = []
        for path in normalized_audio_files:
            escaped_path = path.as_posix().replace("'", "'\\''")
            audio_concat_lines.append(f"file '{escaped_path}'")

        audio_concat_file = work_dir / "concat_audio.txt"
        audio_concat_file.write_text("\n".join(audio_concat_lines), encoding="utf-8")

        master_audio = work_dir / "master_audio.aac"
        _run(
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(audio_concat_file),
                "-c",
                "copy",
                str(master_audio),
            ]
        )

        _run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(master_video),
                "-i",
                str(master_audio),
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                "-movflags",
                "+faststart",
                str(final_path),
            ]
        )
    else:
        shutil.copy(str(master_video), str(final_path))

    return final_path


from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import edge_tts

from app.services.composer import _ffmpeg_executable

LOGGER = logging.getLogger(__name__)

_VI_SIGNAL = re.compile(r"[ăâđêôơưàáạảãằắặẳẵầấậẩẫèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ]", re.I)
DEFAULT_VI_VOICE = "vi-VN-HoaiMyNeural"
DEFAULT_EN_VOICE = "en-US-AvaNeural"

VOICE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "auto",
        "name": "Tự động (Khuyên dùng)",
        "engine": "Auto Neural Engine",
        "model": "Edge-TTS Neural",
        "description": "Tự động phát hiện ngôn ngữ: chọn Hoài Mỹ chuẩn VTV cho Tiếng Việt hoặc Ava cho Tiếng Anh.",
    },
    {
        "id": "vi-VN-HoaiMyNeural",
        "name": "Tiếng Việt — Nữ (Hoài Mỹ)",
        "engine": "Edge-TTS Neural",
        "model": "Microsoft Neural Voice",
        "description": "Giọng nữ VTV truyền cảm, phát âm tròn vành rõ chữ, tự nhiên mượt mà 100% [Mặc định Tiếng Việt].",
    },
    {
        "id": "vi-VN-NamMinhNeural",
        "name": "Tiếng Việt — Nam (Nam Minh)",
        "engine": "Edge-TTS Neural",
        "model": "Microsoft Neural Voice",
        "description": "Giọng nam trầm ấm, rõ ràng, phù hợp bản tin, review sản phẩm, chia sẻ tri thức.",
    },
    {
        "id": "en-US-AvaNeural",
        "name": "English — Female (Ava)",
        "engine": "Edge-TTS Neural",
        "model": "Microsoft Neural Voice",
        "description": "Natural, expressive American English female voice.",
    },
    {
        "id": "en-US-AndrewNeural",
        "name": "English — Male (Andrew)",
        "engine": "Edge-TTS Neural",
        "model": "Microsoft Neural Voice",
        "description": "Professional narrator voice for tech and documentaries.",
    },
    {
        "id": "kokoro-82m",
        "name": "Kokoro 82M AI (ContextBoxAI Fine-Tune Tiếng Việt)",
        "engine": "Kokoro-Vietnamese Native Engine",
        "model": "contextboxai/Kokoro-Vietnamese",
        "description": "Giọng AI Kokoro fine-tune Tiếng Việt (Diễm Trinh / Mai Linh) chạy native local 100% không fallback.",
    },
]


def get_voice_catalog() -> list[dict[str, Any]]:
    return VOICE_CATALOG


VALID_EDGE_VOICES = {
    "vi-VN-HoaiMyNeural",
    "vi-VN-NamMinhNeural",
    "en-US-AvaNeural",
    "en-US-AndrewNeural",
}


def detect_voice(text: str, requested_voice: str = "auto") -> str:
    if requested_voice:
        clean = requested_voice.strip()
        if clean.startswith("edge:"):
            clean = clean[5:]
        if clean in VALID_EDGE_VOICES:
            return clean
    return DEFAULT_VI_VOICE if _VI_SIGNAL.search(text) else DEFAULT_EN_VOICE


def get_audio_duration(audio_path: Path) -> float:
    ffmpeg = _ffmpeg_executable()
    completed = subprocess.run(
        [ffmpeg, "-i", str(audio_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", completed.stderr)
    if match:
        hours = float(match.group(1))
        minutes = float(match.group(2))
        seconds = float(match.group(3))
        total = hours * 3600 + minutes * 60 + seconds
        if total > 0:
            return round(total, 2)
    return 2.5


def create_silent_audio(output_path: Path, duration: float = 2.5) -> float:
    ffmpeg = _ffmpeg_executable()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    codec = "libmp3lame" if output_path.suffix.lower() == ".mp3" else "aac"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-t",
            f"{duration:.3f}",
            "-c:a",
            codec,
            str(output_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return duration


def download_kokoro_model() -> bool:
    model_dir = Path("runtime/models/kokoro")
    model_file = model_dir / "kokoro-v0_19.onnx"
    voices_file = model_dir / "voices.json"
    model_dir.mkdir(parents=True, exist_ok=True)
    if model_file.exists() and voices_file.exists() and model_file.stat().st_size > 100_000_000:
        return True
    try:
        import httpx
        LOGGER.info("Tải file weights Kokoro-82M từ HuggingFace (~310MB)...")
        if not voices_file.exists():
            r = httpx.get("https://huggingface.co/thewh1teagle/Kokoro/resolve/main/voices.json", follow_redirects=True, timeout=60)
            voices_file.write_bytes(r.content)
        if not model_file.exists() or model_file.stat().st_size < 100_000_000:
            with httpx.stream("GET", "https://huggingface.co/thewh1teagle/Kokoro/resolve/main/kokoro-v0_19.onnx", follow_redirects=True, timeout=600) as response:
                with open(model_file, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)
        return model_file.exists() and model_file.stat().st_size > 100_000_000
    except Exception as exc:
        LOGGER.warning("Không thể tự động tải file weight Kokoro-82M: %s", exc)
        return False


def _try_kokoro_tts(text: str, output_path: Path) -> bool:
    try:
        is_vietnamese = bool(_VI_SIGNAL.search(text))
        if is_vietnamese:
            try:
                from kokoro_vietnamese import KokoroVietnamese
                import soundfile as sf
                tts = KokoroVietnamese(voice="diem_trinh", device="cpu")
                audio, phonemes = tts.synthesize(text)
                sf.write(str(output_path), audio, 24000)
                if output_path.exists() and output_path.stat().st_size > 1024:
                    LOGGER.info("Generated Kokoro-Vietnamese fine-tuned AI audio for '%s'", output_path.name)
                    return True
            except Exception as exc:
                LOGGER.warning("KokoroVietnamese fine-tune note: %s", exc)

        from kokoro_onnx import Kokoro
        import soundfile as sf
        model_dir = Path("runtime/models/kokoro")
        weight_dir = Path("weight")

        model_file = model_dir / "kokoro-v0_19.onnx"
        if not model_file.exists() and (weight_dir / "kokoro-v0_19.onnx").exists():
            model_file = weight_dir / "kokoro-v0_19.onnx"

        voices_file = model_dir / "voices.bin"
        if not voices_file.exists() and (weight_dir / "voices.bin").exists():
            voices_file = weight_dir / "voices.bin"
        if not voices_file.exists() and (model_dir / "voices.json").exists():
            voices_file = model_dir / "voices.json"

        if not (model_file.exists() and voices_file.exists()):
            if not download_kokoro_model():
                return False

        kokoro = Kokoro(str(model_file), str(voices_file))
        if is_vietnamese:
            import vig2p
            phonemes = vig2p.phonemize_text(text)
            samples, sample_rate = kokoro.create(phonemes, voice="af_sarah", speed=1.0, lang="en-us", is_phonemes=True)
        else:
            samples, sample_rate = kokoro.create(text, voice="af_sarah", speed=1.0, lang="en-us")

        sf.write(str(output_path), samples, sample_rate)
        return output_path.exists() and output_path.stat().st_size > 1024
    except Exception as exc:
        LOGGER.error("Kokoro ONNX synthesis error: %s", exc)
        return False


def generate_tts_audio(text: str, output_path: Path, voice: str = "auto", max_retries: int = 3) -> float:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    clean_text = text.strip() or "."

    selected_voice = detect_voice(clean_text, voice)

    if voice in {"kokoro-82m", "kokoro"}:
        if _try_kokoro_tts(clean_text, output_path):
            duration = get_audio_duration(output_path)
            LOGGER.info("Generated Kokoro-82M local TTS audio '%s' (duration: %.2fs)", output_path.name, duration)
            return duration
        raise RuntimeError("Không thể tổng hợp giọng đọc Kokoro-82M AI. Vui lòng kiểm tra package kokoro-vietnamese hoặc kokoro-onnx.")

    async def _async_generate() -> None:
        communicate = edge_tts.Communicate(clean_text, selected_voice)
        await communicate.save(str(output_path))

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            asyncio.run(_async_generate())
            if not output_path.exists() or output_path.stat().st_size < 512:
                raise RuntimeError("File âm thanh MP3 từ TTS bị rỗng hoặc lỗi khung hình.")
            duration = get_audio_duration(output_path)
            if duration <= 0.1:
                raise RuntimeError("Thời lượng file âm thanh không hợp lệ.")
            LOGGER.info("Generated Edge-TTS audio '%s' using voice '%s' (duration: %.2fs)", output_path.name, selected_voice, duration)
            return duration
        except Exception as exc:
            last_error = exc
            LOGGER.warning("TTS attempt %d/%d failed for '%s': %s", attempt, max_retries, clean_text[:30], exc)
            if attempt < max_retries:
                time.sleep(1.0)

    LOGGER.warning("TTS synthesis failed after %d retries. Falling back to silent audio: %s", max_retries, last_error)
    return create_silent_audio(output_path, duration=2.5)

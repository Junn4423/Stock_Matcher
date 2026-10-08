from __future__ import annotations

from pathlib import Path
from app.services.tts_service import detect_voice, get_audio_duration


def test_detect_voice() -> None:
    assert detect_voice("Xin chào Việt Nam", "auto") == "vi-VN-HoaiMyNeural"
    assert detect_voice("Hello world", "auto") == "en-US-AvaNeural"
    assert detect_voice("Xin chào", "vi-VN-NamMinhNeural") == "vi-VN-NamMinhNeural"


def test_get_audio_duration_fallback(tmp_path: Path) -> None:
    fake_file = tmp_path / "fake.mp3"
    fake_file.write_text("invalid audio content", encoding="utf-8")
    assert get_audio_duration(fake_file) == 2.5

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models import QueryPlan, Segment, VideoCandidate, VideoFile
from app.services.ranker import rank_candidates

client = TestClient(app)


def test_api_tts_voices_endpoint() -> None:
    response = client.get("/api/tts/voices")
    assert response.status_code == 200
    data = response.json()
    assert "voices" in data
    voice_ids = {v["id"] for v in data["voices"]}
    assert "auto" in voice_ids
    assert "vi-VN-HoaiMyNeural" in voice_ids
    assert "kokoro-82m" in voice_ids


def test_api_pexels_quota_endpoint() -> None:
    response = client.get("/api/pexels/quota")
    assert response.status_code == 200
    data = response.json()
    assert "configured" in data


def test_strict_deduplication_ranking() -> None:
    segment = Segment(index=1, text="Test segment", paragraph_index=1, word_count=2, estimated_seconds=5.0)
    query_plan = QueryPlan(primary_query="test", alternate_queries=[], locale="en-US", visual_intent="test", keywords=["test"])

    file = VideoFile(id=101, quality="hd", file_type="video/mp4", width=1920, height=1080, fps=30, link="https://pexels.com/1.mp4")
    cand1 = VideoCandidate(
        id=101, width=1920, height=1080, url="http://pexels.com/101", image="", duration=10,
        creator_name="Creator A", creator_url="", video_files=[file], source_query="test", source_query_rank=0, result_rank=0
    )
    file2 = VideoFile(id=102, quality="hd", file_type="video/mp4", width=1920, height=1080, fps=30, link="https://pexels.com/2.mp4")
    cand2 = VideoCandidate(
        id=102, width=1920, height=1080, url="http://pexels.com/102", image="", duration=10,
        creator_name="Creator B", creator_url="", video_files=[file2], source_query="test", source_query_rank=0, result_rank=1
    )

    # cand1 used previously
    used_ids = {101}
    match = rank_candidates(segment, query_plan, [cand1, cand2], "landscape", used_ids, {})

    assert match.video is not None
    assert match.video.id == 102  # Must pick unused cand2 instead of used cand1

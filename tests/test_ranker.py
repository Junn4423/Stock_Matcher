from collections import Counter

from app.models import QueryPlan, Segment, VideoCandidate, VideoFile
from app.services.ranker import rank_candidates


def candidate(video_id: int, width: int, height: int, duration: int, rank: int) -> VideoCandidate:
    return VideoCandidate(
        id=video_id,
        width=width,
        height=height,
        url=f"https://www.pexels.com/video/{video_id}/",
        image="",
        duration=duration,
        creator_name=f"Creator {video_id}",
        creator_url="https://www.pexels.com",
        video_files=[VideoFile(video_id, "hd", "video/mp4", width, height, 30, "https://videos.pexels.com/test.mp4")],
        source_query="developer coding",
        source_query_rank=0,
        result_rank=rank,
    )


def test_ranker_prefers_landscape_and_adequate_duration() -> None:
    segment = Segment(1, "Lập trình viên đang viết code.", 1, 6, 5.0)
    plan = QueryPlan("developer coding", [], "en-US", "technology:neutral", ["developer"])
    portrait = candidate(1, 1080, 1920, 10, 0)
    landscape = candidate(2, 1920, 1080, 8, 1)
    match = rank_candidates(segment, plan, [portrait, landscape], "landscape", set(), Counter())
    assert match.video is not None
    assert match.video.id == 2

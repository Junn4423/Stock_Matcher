from __future__ import annotations

import math
from collections import Counter

from app.models import MatchResult, Orientation, QueryPlan, Segment, VideoCandidate, VideoFile


def _orientation_score(width: int, height: int, orientation: Orientation) -> float:
    if width <= 0 or height <= 0:
        return 0.0
    ratio = width / height
    target = {"landscape": 16 / 9, "portrait": 9 / 16, "square": 1.0}[orientation]
    distance = abs(math.log(max(ratio, 0.01) / target))
    return max(0.0, 1.0 - distance / 0.85)


def choose_video_file(candidate: VideoCandidate, orientation: Orientation) -> VideoFile | None:
    files = [
        file
        for file in candidate.video_files
        if file.link and "mp4" in file.file_type.lower() and file.width > 0 and file.height > 0
    ]
    if not files:
        return None

    target_width, target_height = {
        "landscape": (1920, 1080),
        "portrait": (1080, 1920),
        "square": (1080, 1080),
    }[orientation]

    def score(file: VideoFile) -> tuple[float, float, float]:
        orientation_fit = _orientation_score(file.width, file.height, orientation)
        pixel_distance = abs(file.width - target_width) + abs(file.height - target_height)
        adequate = 1.0 if file.width >= target_width * 0.8 and file.height >= target_height * 0.8 else 0.0
        # Ưu tiên gần Full HD thay vì tải file 4K quá lớn khi không cần thiết.
        return adequate, orientation_fit, -pixel_distance

    return max(files, key=score)


def rank_candidates(
    segment: Segment,
    query_plan: QueryPlan,
    candidates: list[VideoCandidate],
    orientation: Orientation,
    used_video_ids: set[int],
    creator_usage: Counter[str],
) -> MatchResult:
    best: tuple[float, VideoCandidate, VideoFile, list[str]] | None = None

    for candidate in candidates:
        selected_file = choose_video_file(candidate, orientation)
        if selected_file is None:
            continue

        reasons: list[str] = []
        score = 0.0

        query_score = max(0.0, 1.0 - candidate.source_query_rank * 0.16)
        rank_score = 1.0 / math.log2(candidate.result_rank + 2)
        score += 3.0 * query_score + 2.2 * rank_score
        reasons.append(f"query={query_score:.2f}")

        orientation_fit = _orientation_score(selected_file.width, selected_file.height, orientation)
        score += 2.4 * orientation_fit
        reasons.append(f"orientation={orientation_fit:.2f}")

        pixels = selected_file.width * selected_file.height
        resolution_score = min(1.0, pixels / (1920 * 1080))
        score += 1.35 * resolution_score
        reasons.append(f"resolution={resolution_score:.2f}")

        needed = segment.estimated_seconds
        if candidate.duration >= needed:
            duration_score = min(1.0, needed / max(candidate.duration, 1) + 0.35)
        else:
            duration_score = max(0.0, candidate.duration / max(needed, 0.1) - 0.25)
        score += 1.6 * duration_score
        reasons.append(f"duration={duration_score:.2f}")

        if candidate.id in used_video_ids:
            score -= 100.0
            reasons.append("duplicate=-100.0")

        creator_count = creator_usage.get(candidate.creator_name, 0)
        if creator_count:
            penalty = min(1.4, creator_count * 0.35)
            score -= penalty
            reasons.append(f"creator_repeat=-{penalty:.2f}")

        # Topic & Visual Intent Relevance Bonus
        topic_matches = sum(1 for kw in query_plan.keywords if kw.lower() in candidate.url.lower() or kw.lower() in candidate.source_query.lower())
        if topic_matches:
            bonus = min(2.0, topic_matches * 0.5)
            score += bonus
            reasons.append(f"topic_match=+{bonus:.2f}")


        if best is None or score > best[0]:
            best = (score, candidate, selected_file, reasons)


    if best is None:
        return MatchResult(
            segment=segment,
            query_plan=query_plan,
            video=None,
            selected_file=None,
            score=0.0,
            score_reasons=["Không có candidate MP4 phù hợp."],
        )

    score, video, selected_file, reasons = best
    return MatchResult(
        segment=segment,
        query_plan=query_plan,
        video=video,
        selected_file=selected_file,
        score=score,
        score_reasons=reasons,
    )

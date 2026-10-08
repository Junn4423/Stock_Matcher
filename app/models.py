from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Orientation = Literal["landscape", "portrait", "square"]
SegmentMode = Literal["smart", "sentence", "paragraph"]


@dataclass(slots=True)
class Segment:
    index: int
    text: str
    paragraph_index: int
    word_count: int
    estimated_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QueryPlan:
    primary_query: str
    alternate_queries: list[str]
    locale: str
    visual_intent: str
    keywords: list[str]

    @property
    def all_queries(self) -> list[str]:
        result: list[str] = []
        for query in [self.primary_query, *self.alternate_queries]:
            normalized = " ".join(query.split()).strip()
            if normalized and normalized.lower() not in {x.lower() for x in result}:
                result.append(normalized)
        return result


@dataclass(slots=True)
class VideoFile:
    id: int
    quality: str
    file_type: str
    width: int
    height: int
    fps: float
    link: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "VideoFile":
        return cls(
            id=int(data.get("id") or 0),
            quality=str(data.get("quality") or ""),
            file_type=str(data.get("file_type") or ""),
            width=int(data.get("width") or 0),
            height=int(data.get("height") or 0),
            fps=float(data.get("fps") or 0),
            link=str(data.get("link") or ""),
        )


@dataclass(slots=True)
class VideoCandidate:
    id: int
    width: int
    height: int
    url: str
    image: str
    duration: int
    creator_name: str
    creator_url: str
    video_files: list[VideoFile]
    source_query: str
    source_query_rank: int
    result_rank: int

    @classmethod
    def from_api(
        cls,
        data: dict[str, Any],
        source_query: str,
        source_query_rank: int,
        result_rank: int,
    ) -> "VideoCandidate":
        user = data.get("user") or {}
        return cls(
            id=int(data.get("id") or 0),
            width=int(data.get("width") or 0),
            height=int(data.get("height") or 0),
            url=str(data.get("url") or ""),
            image=str(data.get("image") or ""),
            duration=int(data.get("duration") or 0),
            creator_name=str(user.get("name") or "Unknown creator"),
            creator_url=str(user.get("url") or ""),
            video_files=[VideoFile.from_api(item) for item in data.get("video_files") or []],
            source_query=source_query,
            source_query_rank=source_query_rank,
            result_rank=result_rank,
        )


@dataclass(slots=True)
class MatchResult:
    segment: Segment
    query_plan: QueryPlan
    video: VideoCandidate | None
    selected_file: VideoFile | None
    score: float
    score_reasons: list[str] = field(default_factory=list)
    local_video_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment": self.segment.to_dict(),
            "query_plan": asdict(self.query_plan),
            "video": asdict(self.video) if self.video else None,
            "selected_file": asdict(self.selected_file) if self.selected_file else None,
            "score": round(self.score, 4),
            "score_reasons": self.score_reasons,
            "local_video_path": self.local_video_path,
        }


@dataclass(slots=True)
class ProcessOptions:
    segment_mode: SegmentMode = "smart"
    orientation: Orientation = "landscape"
    min_segment_words: int = 7
    max_segment_words: int = 34
    words_per_minute: int = 150
    max_queries_per_segment: int = 2
    results_per_query: int = 18
    download_videos: bool = False
    build_rough_cut: bool = False
    enable_tts: bool = True
    tts_voice: str = "auto"
    transition_duration: float = 0.4

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

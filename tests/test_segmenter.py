from app.models import ProcessOptions
from app.services.segmenter import segment_text, split_sentences


def test_sentence_split_keeps_common_abbreviation() -> None:
    parts = split_sentences("Dr. Smith builds software. Sau đó nhóm kiểm thử sản phẩm.")
    assert len(parts) == 2
    assert parts[0].startswith("Dr. Smith")


def test_smart_segmentation_merges_short_fragments() -> None:
    options = ProcessOptions(segment_mode="smart", min_segment_words=6, max_segment_words=20)
    segments = segment_text(
        "AI phát triển nhanh. Nó hỗ trợ doanh nghiệp. Tuy nhiên, dữ liệu phải được bảo vệ cẩn thận.",
        options,
    )
    assert 1 <= len(segments) <= 3
    assert all(segment.word_count <= 20 for segment in segments)
    assert all(segment.estimated_seconds >= 2.5 for segment in segments)

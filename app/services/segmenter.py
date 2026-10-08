from __future__ import annotations

import re
from collections.abc import Iterable

from app.models import ProcessOptions, Segment


_ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.", "vs.", "etc.",
    "e.g.", "i.e.", "u.s.", "u.k.", "tp.", "tp.hcm.", "p.g.s.", "ts.",
    "th.s.", "bs.", "ks.", "stt.", "q.", "p.", "h.", "t.",
}

_BULLET_PREFIX = re.compile(r"^\s*(?:[-*•‣▪◦]|\d+[.)]|[A-Za-z][.)])\s+")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])(?:[\"'”’»)]*)\s+(?=[A-ZÀ-Ỹ0-9\"'“‘«(])")
_SOFT_SPLIT = re.compile(
    r"(?:(?<=[,;:])\s+|\s+(?=(?:nhưng|tuy nhiên|vì vậy|do đó|đồng thời|trong khi|"
    r"however|therefore|meanwhile|because|although|while|and|but)\b))",
    flags=re.IGNORECASE,
)
_WORD_RE = re.compile(r"[\wÀ-ỹ]+(?:[-'][\wÀ-ỹ]+)?", flags=re.UNICODE)


def _protect_abbreviations(text: str) -> str:
    protected = text
    for abbreviation in sorted(_ABBREVIATIONS, key=len, reverse=True):
        pattern = re.compile(re.escape(abbreviation), flags=re.IGNORECASE)
        protected = pattern.sub(lambda m: m.group(0).replace(".", "<DOT>"), protected)
    protected = re.sub(r"(?<=\b[A-ZÀ-Ỹ])\.(?=[A-ZÀ-Ỹ]\.)", "<DOT>", protected)
    return protected


def _restore_abbreviations(text: str) -> str:
    return text.replace("<DOT>", ".")


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def split_sentences(paragraph: str) -> list[str]:
    paragraph = " ".join(paragraph.split()).strip()
    if not paragraph:
        return []

    protected = _protect_abbreviations(paragraph)
    parts = _SENTENCE_BOUNDARY.split(protected)
    restored = [_restore_abbreviations(part).strip() for part in parts if part.strip()]
    return restored or [paragraph]


def _split_long_piece(text: str, max_words: int) -> list[str]:
    if word_count(text) <= max_words:
        return [text.strip()]

    chunks = [chunk.strip() for chunk in _SOFT_SPLIT.split(text) if chunk.strip()]
    if len(chunks) <= 1:
        words = text.split()
        return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]

    result: list[str] = []
    current: list[str] = []
    current_words = 0
    for chunk in chunks:
        count = word_count(chunk)
        if current and current_words + count > max_words:
            result.append(" ".join(current).strip())
            current, current_words = [], 0
        current.append(chunk)
        current_words += count
    if current:
        result.append(" ".join(current).strip())
    return result


def _merge_short_pieces(pieces: Iterable[str], min_words: int, max_words: int) -> list[str]:
    result: list[str] = []
    buffer = ""

    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if not buffer:
            buffer = piece
            continue

        combined = f"{buffer} {piece}".strip()
        if word_count(buffer) < min_words and word_count(combined) <= max_words:
            buffer = combined
        else:
            result.append(buffer)
            buffer = piece

    if buffer:
        if result and word_count(buffer) < min_words and word_count(result[-1] + " " + buffer) <= max_words:
            result[-1] = f"{result[-1]} {buffer}".strip()
        else:
            result.append(buffer)
    return result


def _paragraphs(text: str) -> list[str]:
    raw_paragraphs = re.split(r"\n\s*\n", text)
    paragraphs: list[str] = []
    for raw in raw_paragraphs:
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if not lines:
            continue
        current: list[str] = []
        for line in lines:
            if _BULLET_PREFIX.match(line):
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
                paragraphs.append(_BULLET_PREFIX.sub("", line).strip())
            else:
                current.append(line)
        if current:
            paragraphs.append(" ".join(current))
    return paragraphs


def segment_text(text: str, options: ProcessOptions) -> list[Segment]:
    segments: list[Segment] = []
    index = 1

    for paragraph_index, paragraph in enumerate(_paragraphs(text), start=1):
        if options.segment_mode == "paragraph":
            pieces = _split_long_piece(paragraph, options.max_segment_words)
        elif options.segment_mode == "sentence":
            pieces = []
            for sentence in split_sentences(paragraph):
                pieces.extend(_split_long_piece(sentence, options.max_segment_words))
        else:
            raw_pieces: list[str] = []
            for sentence in split_sentences(paragraph):
                raw_pieces.extend(_split_long_piece(sentence, options.max_segment_words))
            pieces = _merge_short_pieces(
                raw_pieces,
                min_words=options.min_segment_words,
                max_words=options.max_segment_words,
            )

        for piece in pieces:
            count = word_count(piece)
            if count == 0:
                continue
            seconds = max(2.5, (count / max(options.words_per_minute, 60)) * 60 + 0.7)
            segments.append(
                Segment(
                    index=index,
                    text=piece.strip(),
                    paragraph_index=paragraph_index,
                    word_count=count,
                    estimated_seconds=round(seconds, 2),
                )
            )
            index += 1

    return segments

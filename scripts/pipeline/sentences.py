"""Split a Whisper transcript into sentences that remember their segments.

The adjudication unit is the sentence (TRANSCRIPT_VERIFICATION_DESIGN, round
4: "word-level signals only LOCATE uncertainty; the judge always rules on the
full sentence").  The *storage* unit is the Whisper segment.  This module is
the bridge: every :class:`Sentence` knows which segments it spans and where it
sits inside each of them, so a ruling on a sentence can be written back as a
minimal edit to one segment's text rather than a rewrite.

Sentence splitting is deliberately crude -- prompted Whisper emits properly
punctuated prose (ASR_SHOWDOWN section 4: 422 sentence terminators in a
32-minute video against 19 unprompted), so terminal punctuation is a real
signal here rather than a guess.  A "sentence" that has no terminator simply
runs to the end of its segment run, which is the right conservative answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

#: Segments are joined with a single space so a character offset in the joined
#: text maps deterministically onto one segment.
JOIN = " "

_TERMINATOR_RE = re.compile(r"[.!?]+[\"')\]]*(?:\s+|$)")

#: Whisper's punctuation discipline is good but not universal -- on
#: ``-zr_N8CDKUA`` it stops emitting terminators around the 15-minute mark and
#: produces one 7 775-character "sentence" covering 17 minutes of audio. A run
#: that long is useless as an adjudication unit (and blows the judge's
#: context), so oversized runs are split at *segment* boundaries: never
#: mid-segment, so a correction still maps onto exactly one stored row.
MAX_SENTENCE_CHARS = 400


@dataclass
class SegmentSpan:
    """Where one segment sits inside the joined draft text."""

    segment_index: int
    start_char: int
    end_char: int
    start: float
    end: float
    text: str


@dataclass
class Sentence:
    """One adjudication unit."""

    index: int
    text: str
    start_char: int
    end_char: int
    start: float
    end: float
    segment_indices: List[int] = field(default_factory=list)


def build_draft(segments: Sequence[dict]) -> Tuple[str, List[SegmentSpan]]:
    """Join segments into one draft string and record each one's char range."""
    parts: List[str] = []
    spans: List[SegmentSpan] = []
    cursor = 0
    for index, seg in enumerate(segments):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if parts:
            cursor += len(JOIN)
            parts.append(JOIN)
        start = float(seg.get("start") if seg.get("start") is not None
                      else seg.get("start_seconds") or 0.0)
        end = seg.get("end")
        if end is None:
            end = start + float(seg.get("duration_seconds") or 0.0)
        spans.append(SegmentSpan(segment_index=index, start_char=cursor,
                                 end_char=cursor + len(text),
                                 start=start, end=float(end), text=text))
        parts.append(text)
        cursor += len(text)
    return "".join(parts), spans


def _segments_covering(spans: Sequence[SegmentSpan],
                       start_char: int, end_char: int) -> List[SegmentSpan]:
    return [s for s in spans if s.start_char < end_char and s.end_char > start_char]


def _split_oversized(boundaries: List[Tuple[int, int]],
                     spans: Sequence[SegmentSpan],
                     limit: int = MAX_SENTENCE_CHARS) -> List[Tuple[int, int]]:
    """Break runs longer than ``limit`` at the segment boundaries inside them."""
    if not spans:
        return boundaries
    cuts = [s.start_char for s in spans]
    out: List[Tuple[int, int]] = []
    for start_char, end_char in boundaries:
        if end_char - start_char <= limit:
            out.append((start_char, end_char))
            continue
        cursor = start_char
        while end_char - cursor > limit:
            candidates = [c for c in cuts if cursor < c <= cursor + limit]
            if not candidates:
                # one segment is longer than the limit all by itself: keep it
                # whole rather than cutting mid-segment.
                nxt = [c for c in cuts if c > cursor]
                if not nxt or nxt[0] >= end_char:
                    break
                candidates = [nxt[0]]
            cut = candidates[-1]
            out.append((cursor, cut))
            cursor = cut
        if cursor < end_char:
            out.append((cursor, end_char))
    return out


def split_sentences(draft: str, spans: Sequence[SegmentSpan]) -> List[Sentence]:
    """Split ``draft`` into :class:`Sentence` objects anchored to ``spans``."""
    boundaries: List[Tuple[int, int]] = []
    cursor = 0
    for match in _TERMINATOR_RE.finditer(draft):
        end = match.end()
        # Trailing whitespace belongs to neither sentence.
        text_end = match.end() - (len(match.group()) - len(match.group().rstrip()))
        if text_end <= cursor:
            continue
        boundaries.append((cursor, text_end))
        cursor = end
    if cursor < len(draft.rstrip()):
        boundaries.append((cursor, len(draft.rstrip())))

    boundaries = _split_oversized(boundaries, spans)

    sentences: List[Sentence] = []
    for index, (start_char, end_char) in enumerate(boundaries):
        text = draft[start_char:end_char].strip()
        if not text:
            continue
        # re-anchor start_char after the strip so offsets stay exact
        lead = len(draft[start_char:end_char]) - len(draft[start_char:end_char].lstrip())
        start_char += lead
        end_char = start_char + len(text)
        covering = _segments_covering(spans, start_char, end_char)
        if covering:
            t0 = min(s.start for s in covering)
            t1 = max(s.end for s in covering)
            seg_indices = [s.segment_index for s in covering]
        else:  # pragma: no cover - only when spans is empty
            t0 = t1 = 0.0
            seg_indices = []
        sentences.append(Sentence(index=len(sentences), text=text,
                                  start_char=start_char, end_char=end_char,
                                  start=t0, end=t1, segment_indices=seg_indices))
    return sentences


def sentences_from_segments(segments: Sequence[dict]):
    """Convenience: ``(draft, spans, sentences)`` for a segment list."""
    draft, spans = build_draft(segments)
    return draft, spans, split_sentences(draft, spans)

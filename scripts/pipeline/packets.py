"""Build production adjudication packets from a Whisper draft + witnesses.

Same shape as ``tools/tournament/build_packets.py`` emitted, so
``tools/tournament/judge_prompt.build_prompt`` can be reused *unchanged* --
the prompt the production judge sees is byte-for-byte the prompt the ``full``
ablation cell was scored on (style card v1.1 + entity roster + disagreement
flags).  Deviating from that would throw away the tournament's evidence.

Two things the tournament did not have to do:

* **Chunking.**  A tournament packet was a 40-second passage.  A video is 30+
  minutes, so witnesses are compared inside 60-second windows and the judge is
  handed one small packet per run of flagged sentences.
* **Sentence selection.**  Only sentences carrying a disagreement flag or a
  low-confidence Whisper word are put up for judgement.  The `bare` ablation
  (raw transcript, no flags) scored **WER +0.176** with 17 false corrections:
  a judge handed unflagged text invents errors.  Unflagged sentences ride
  along as read-only context and are never offered for a ruling.

Pure functions; no network, no database.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from scripts.pipeline import flags as flagmod
from scripts.pipeline.sentences import Sentence, SegmentSpan

#: Sentences of context on each side of a flagged run.  The judge rules on the
#: flagged sentence but has to see what it sits between to know whether it
#: "reads as something a human actually said".
CONTEXT_SENTENCES = 2

#: Cap on flagged spans quoted into one packet -- past this the judge gets
#: anxious and escalation-happy (TOURNAMENT_RESULTS, "Flags are double-edged").
MAX_FLAGS_PER_PACKET = 12

MAX_LOWCONF_PER_PACKET = 10


def build_windows(spans: Sequence[SegmentSpan],
                  window_seconds: float = flagmod.DEFAULT_WINDOW_SECONDS
                  ) -> List[List[SegmentSpan]]:
    """Group segment spans into contiguous time windows."""
    windows: List[List[SegmentSpan]] = []
    current: List[SegmentSpan] = []
    window_start: Optional[float] = None
    for span in spans:
        if window_start is None:
            window_start = span.start
        if current and span.start - window_start >= window_seconds:
            windows.append(current)
            current = []
            window_start = span.start
        current.append(span)
    if current:
        windows.append(current)
    return windows


def compute_flags(draft: str,
                  spans: Sequence[SegmentSpan],
                  youtube_segments: Sequence[dict],
                  window_seconds: float = flagmod.DEFAULT_WINDOW_SECONDS
                  ) -> List[dict]:
    """Word-level disagreements between the Whisper draft and YouTube ASR.

    Witnesses are aligned inside time windows; a ``SequenceMatcher`` run over a
    whole 30-minute video against a witness that drifts anywhere produces
    opcodes that mean nothing.
    """
    if not youtube_segments:
        return []
    out: List[dict] = []
    for window in build_windows(spans, window_seconds):
        start = window[0].start
        end = window[-1].end
        offset = window[0].start_char
        window_text = draft[offset:window[-1].end_char]
        yt = flagmod.segments_in_window(youtube_segments, start, end)
        yt_text = flagmod.join_segments(yt)
        if not yt_text:
            continue
        out.extend(flagmod.disagreement_flags(
            window_text, {"youtube": yt_text}, char_offset=offset))
    return out


def _witness_excerpt(segments: Sequence[dict], start: float, end: float) -> str:
    return flagmod.join_segments(flagmod.segments_in_window(segments, start, end))


def build_packet(video: dict,
                 roster: dict,
                 sentences: Sequence[Sentence],
                 group: Sequence[int],
                 all_flags: Sequence[dict],
                 lows: Sequence[dict],
                 youtube_segments: Sequence[dict],
                 packet_id: str) -> dict:
    """One packet: a run of flagged sentences plus their context."""
    lo = max(0, group[0] - CONTEXT_SENTENCES)
    hi = min(len(sentences) - 1, group[-1] + CONTEXT_SENTENCES)
    context = list(sentences[lo:hi + 1])
    under_review = [sentences[i] for i in group]

    start = min(s.start for s in context)
    end = max(s.end for s in context)

    packet_flags: List[dict] = []
    packet_lows: List[dict] = []
    for sentence in under_review:
        packet_flags.extend(flagmod.flags_for_sentence(sentence, all_flags))
        packet_lows.extend(flagmod.lows_for_sentence(sentence, lows))

    # de-duplicate while preserving order
    seen = set()
    deduped = []
    for flag in packet_flags:
        key = (flag.get("start_char"), flag.get("end_char"), flag.get("span"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(flag)

    draft_text = " ".join(s.text for s in context)
    witnesses = {"whisper": {"segments": [], "text": draft_text}}
    yt_text = _witness_excerpt(youtube_segments, start, end)
    if yt_text:
        witnesses["youtube"] = {"segments": [], "text": yt_text}

    return {
        "packet_id": packet_id,
        "passage": packet_id,
        "passage_window": [round(start, 2), round(end, 2)],
        "passage_label": "flagged span review",
        "witness_set": "W+YT" if yt_text else "W",
        "video": video,
        "entity_roster": roster,
        "witnesses": witnesses,
        "draft_transcript": draft_text,
        "disagreement_flags": [
            {"whisper_span": f["span"], "context": f["context"],
             "alternatives": f["alternatives"],
             "start_char": f["start_char"], "end_char": f["end_char"]}
            for f in deduped[:MAX_FLAGS_PER_PACKET]
        ],
        "whisper_low_confidence": sorted(
            {(l["word"], l["t"]): l for l in packet_lows}.values(),
            key=lambda x: x["p"])[:MAX_LOWCONF_PER_PACKET],
        # not shown to the judge; used to attach its rulings back to sentences
        "_sentence_indices": list(group),
        "_context_indices": list(range(lo, hi + 1)),
    }


def build_roster(people: Sequence[dict], dogs: Sequence[dict],
                 domain_terms: Optional[Sequence[str]] = None) -> dict:
    """Entity roster in the shape ``judge_prompt.build_prompt`` expects.

    The roster is what recovers nicknames: 4 of 10 screening judges got
    "Captain Teeny Trout" and all four did it by matching the draft against an
    alias here, not from context (TOURNAMENT_RESULTS, finding 3).
    """
    return {
        "people": [{"name": p["name"], "aliases": list(p.get("aliases") or [])}
                   for p in people],
        "dogs": [{"name": d["name"], "breed": d.get("breed")} for d in dogs],
        "domain_terms": list(domain_terms or [
            "crappie", "crappies", "bluegill", "bluegills", "gills",
            "Boundary Waters", "steel eater", "SS Tin Can", "quinzee",
            "hot tent", "portage", "bushcraft",
        ]),
    }

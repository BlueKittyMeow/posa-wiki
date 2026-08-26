#!/usr/bin/env python3
"""Assemble the judge prompt from a sealed packet + ablation flags.

Ablation dimensions (TRANSCRIPT_VERIFICATION_DESIGN, round 3):
  style : include the Posa style card (register definition)
  lex   : include the entity roster / domain lexicon
  flags : include the disagreement flags + low-confidence words
          (when False the judge gets the raw transcript and must locate its own
           uncertainty)

The packet contains no ground truth. Nothing in this module may import score.py.
"""
import json
from pathlib import Path

STYLE_CARD = Path(__file__).resolve().parents[2] / "docs/research/POSA_STYLE_CARD.md"

ROLE = """You are the JUDGE in a transcript verification court.

WITNESSES are independent automatic speech recognition systems. They each
produced a transcript of the same audio. They are not experts and they do not
agree. You never listen to audio and you never transcribe: you read conflicting
testimony plus context, and you rule.

Your rulings are candidate corrections only. A human reviews everything."""

TASK_FLAGGED = """For EACH flagged span below, rule on the FULL SENTENCE OR UTTERANCE that
contains it — word-level flags only locate the uncertainty, they are not the
unit of judgement. Your ruling must yield a sentence that reads as something a
human actually said aloud.

Verdicts:
  "confirm"  - the draft reading is right as it stands.
  "correct"  - the draft is wrong and you know what was said. Supply the
               corrected sentence.
  "escalate" - genuinely uncertain; a human must listen. Say what the
               competing readings are."""

TASK_UNFLAGGED = """Read the draft transcript and identify the spans you believe are
transcription errors. For EACH one, rule on the FULL SENTENCE OR UTTERANCE that
contains it. Your ruling must yield a sentence that reads as something a human
actually said aloud.

Verdicts:
  "confirm"  - (use sparingly) a span that looks odd but is right as it stands.
  "correct"  - the draft is wrong and you know what was said. Supply the
               corrected sentence.
  "escalate" - genuinely uncertain; a human must listen."""

OUTPUT_SPEC = """OUTPUT FORMAT — a JSON array and nothing else. No preamble, no markdown
fence, no commentary. Each element:

{"span": "<the disputed words as they appear in the draft>",
 "verdict": "confirm" | "correct" | "escalate",
 "correction": "<the full corrected sentence, or null for confirm/escalate>",
 "reasoning": "<one line>"}

If you have no rulings to make, output []."""

GENERIC_CAUTION = """CAUTION: changing text that was already correct into something merely
plausible is worse than useless. When unsure, escalate."""


def build_prompt(packet, style=True, lex=True, flags=True, extra_caution=None):
    """Assemble the judge prompt.

    ``extra_caution`` is appended verbatim after the task description. It
    defaults to None so every tournament cell reproduces byte-for-byte; the
    production pipeline passes a contraction/register guard through it (see
    ``scripts/pipeline/judge_batch.CONTRACTION_GUARD``).
    """
    return _build_prompt(packet, style, lex, flags, extra_caution)


def _build_prompt(packet, style=True, lex=True, flags=True, extra_caution=None):
    p = packet
    parts = [ROLE, ""]

    parts.append("=== CASE ===")
    parts.append(f"Video: {p['video']['title']}")
    if p["video"].get("description"):
        parts.append("Video description (author-written):")
        parts.append(p["video"]["description"].strip()[:1200])
    parts.append(f"Passage: {p['passage_label']} "
                 f"({p['passage_window'][0]:.0f}s-{p['passage_window'][1]:.0f}s)")
    parts.append("")

    if style:
        card = STYLE_CARD.read_text()
        parts.append("=== HOW THIS SPEAKER TALKS (style card) ===")
        parts.append(card)
        parts.append("")
    else:
        parts.append("=== NOTE ===")
        parts.append(GENERIC_CAUTION)
        parts.append("")

    if lex:
        r = p["entity_roster"]
        parts.append("=== ENTITY ROSTER (canonical spellings) ===")
        for person in r["people"]:
            al = f"  (also: {', '.join(person['aliases'])})" if person["aliases"] else ""
            parts.append(f"  PERSON: {person['name']}{al}")
        for n in r.get("nicknames_in_play", []):
            parts.append(f"  NICKNAME IN PLAY: {n}")
        for d in r["dogs"]:
            parts.append(f"  DOG: {d['name']}")
        parts.append("  DOMAIN TERMS: " + ", ".join(r["domain_terms"]))
        parts.append("")

    parts.append("=== TESTIMONY ===")
    names = {"whisper": "WITNESS 1 (Whisper large-v3)",
             "youtube": "WITNESS 2 (YouTube auto-captions)",
             "parakeet": "WITNESS 3 (Parakeet TDT)"}
    for k, v in p["witnesses"].items():
        parts.append(f"--- {names.get(k, k)} ---")
        parts.append(v["text"])
        parts.append("")

    parts.append("=== DRAFT TRANSCRIPT UNDER REVIEW (Witness 1) ===")
    parts.append(p["draft_transcript"])
    parts.append("")

    if flags:
        if p["disagreement_flags"]:
            parts.append("=== FLAGGED SPANS (witnesses disagree here) ===")
            for i, f in enumerate(p["disagreement_flags"], 1):
                alts = "; ".join(f"{k} heard \"{v}\"" for k, v in f["alternatives"].items())
                parts.append(f'{i}. draft: "{f["whisper_span"]}"  '
                             f'[context: ...{f["context"]}...]  -> {alts}')
            parts.append("")
        if p["whisper_low_confidence"]:
            parts.append("=== LOW-CONFIDENCE WORDS (Witness 1 self-reported) ===")
            parts.append(", ".join(f'"{w["word"]}" (p={w["p"]})'
                                   for w in p["whisper_low_confidence"][:15]))
            parts.append("")
        parts.append(TASK_FLAGGED)
    else:
        parts.append(TASK_UNFLAGGED)

    if extra_caution:
        parts.append("")
        parts.append(extra_caution)

    parts.append("")
    parts.append(OUTPUT_SPEC)
    return "\n".join(parts)


ABLATIONS = {
    "full":    dict(style=True,  lex=True,  flags=True),
    "noStyle": dict(style=False, lex=True,  flags=True),
    "noLex":   dict(style=True,  lex=False, flags=True),
    "noFlags": dict(style=True,  lex=True,  flags=False),
    "bare":    dict(style=False, lex=False, flags=False),
}


if __name__ == "__main__":
    import sys
    pk = json.loads(Path(sys.argv[1]).read_text())
    abl = ABLATIONS[sys.argv[2] if len(sys.argv) > 2 else "full"]
    print(build_prompt(pk, **abl))

"""Turn a judge's corrected sentence into minimal per-segment edits.

The tournament scorer got this wrong three times (TOURNAMENT_RESULTS, "What
remains untested": *"a correction-applier that scrambled text when models
emitted one-word spans"*), so this module is built the other way round: it
never trusts the model's ``span`` field, and it never rewrites a sentence.

It diffs the draft sentence against the model's corrected sentence, keeps only
the token runs that actually changed, maps each changed run back to the one
Whisper segment that owns it, and returns a character-level splice.  A change
that straddles two segments, or a "correction" that rewrites most of the
sentence, is refused and reported -- refusing is always safe, because a
refused correction becomes an escalation and a human sees it.

No network, no database, no model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Sequence, Tuple

from scripts.pipeline.flags import (
    CONTRACTION_EXPANSIONS, FILLERS, normalise_word)

_WORD_RE = re.compile(r"[A-Za-z0-9']+")

#: A "correction" that changes more than this fraction of a sentence's tokens
#: is a rewrite, not a repair.  `gutenberg-12b` finished last in the
#: tournament by doing exactly that (10 false corrections, WER +0.420).
MAX_CHANGED_FRACTION = 0.6

#: Below this many tokens the fraction test is meaningless (60 % of three
#: words rounds down to one).  Short sentences instead get the rule that at
#: least one word must survive: a "correction" that replaces every word of
#: "All right, Monty." with "monte come on out" is a substitution, not a
#: repair, and the live run produced exactly that.
SHORT_SENTENCE_TOKENS = 5


def _bare(word: str) -> str:
    """Lowercase, possessive-stripped form: ``Layla's`` -> ``layla``."""
    word = normalise_word(word).lower()
    word = re.sub(r"'s$", "", word)
    return word.replace("'", "")


def degrades_casing(before: str, after: str) -> bool:
    """True when a replacement drops capitalisation the draft had.

    The YouTube witness is entirely lowercase and unpunctuated. When a judge
    splices from it, the giveaway is casing: ``"Layla's"`` comes back as
    ``"leila's"``, ``"Seeing as how"`` as ``"see is how"``. Whisper's casing is
    good and the other witness has none, so a correction that *removes* a
    capital is importing the wrong witness's style, not fixing a word.
    """
    before_words = before.split()
    after_words = after.split()
    if not before_words or not after_words:
        return False
    return before_words[0][:1].isupper() and after_words[0][:1].islower()


def breaks_entity_name(before: str, after: str, roster_names) -> bool:
    """True when a correction rewrites a canonical entity name into a non-name.

    The roster exists to *recover* names — 4 of 10 tournament judges got
    "Captain Teeny Trout" by matching against it. A ruling that runs the other
    way, turning ``"Layla"`` into ``"leila"`` or ``"Rueger"`` into something
    absent from the roster, is using the lexicon backwards and is always
    wrong.
    """
    canonical = {_bare(n) for name in (roster_names or []) for n in name.split()}
    canonical.discard("")
    if not canonical:
        return False
    before_set = {_bare(w) for w in _WORD_RE.findall(before)}
    after_set = {_bare(w) for w in _WORD_RE.findall(after)}
    lost = (before_set & canonical) - after_set
    return bool(lost)


def is_register_smoothing(before: str, after: str) -> bool:
    """True when an edit only formalises casual speech.

    ``"wanna"`` -> ``"want to"`` is not a transcription correction, it is the
    judge tidying up how someone talks.  Measured in the first live run.
    """
    key = normalise_word(before.strip()).lower()
    target = re.sub(r"\s+", " ", after.strip().lower()).strip(" .,!?")
    expansions = CONTRACTION_EXPANSIONS.get(key)
    return bool(expansions and target in expansions)


@dataclass
class Edit:
    """One character splice inside one segment."""

    segment_index: int
    start_char: int          # offset within the segment's own text
    end_char: int
    replacement: str
    before: str


@dataclass
class CorrectionPlan:
    """The result of planning a correction."""

    edits: List[Edit]
    refusals: List[str]
    changed_tokens: int
    applicable: bool

    @property
    def is_null(self) -> bool:
        return self.changed_tokens == 0


def _tokens(text: str) -> List[Tuple[str, int, int]]:
    """``(normalised, start, end)`` for every word, fillers included.

    Unlike :func:`scripts.pipeline.flags.tokenize` fillers are *kept* here --
    dropping "uh" while planning an edit would make the offsets lie.
    """
    return [(normalise_word(m.group()), m.start(), m.end())
            for m in _WORD_RE.finditer(text)]


def _comparable(tokens: Sequence[Tuple[str, int, int]]) -> List[str]:
    """Filler-insensitive view for diffing (fillers never justify an edit)."""
    return [t if t not in FILLERS else "\x00filler" for t, _s, _e in tokens]


def plan_correction(draft_sentence: str,
                    correction: str,
                    segment_spans: Sequence["object"],
                    sentence_start_char: int,
                    roster_names: Sequence[str] = ()) -> CorrectionPlan:
    """Plan the edits that turn ``draft_sentence`` into ``correction``.

    ``segment_spans`` are :class:`scripts.pipeline.sentences.SegmentSpan`
    objects for the whole video; ``sentence_start_char`` is where the sentence
    begins in the joined draft, so a token offset inside the sentence can be
    turned into an absolute offset and looked up against them.
    """
    refusals: List[str] = []
    draft_tokens = _tokens(draft_sentence)
    corr_tokens = _tokens(correction or "")

    if not (correction or "").strip():
        return CorrectionPlan([], ["empty correction"], 0, False)

    matcher = SequenceMatcher(a=_comparable(draft_tokens),
                              b=_comparable(corr_tokens), autojunk=False)
    opcodes = [op for op in matcher.get_opcodes() if op[0] != "equal"]

    changed = sum(max(op[2] - op[1], op[4] - op[3]) for op in opcodes)
    if changed == 0:
        # The model said "correct" and changed nothing: a null correction, the
        # failure mode the tournament counted in its `null corr` column.
        return CorrectionPlan([], ["null correction (text unchanged)"], 0, False)

    budget = (max(1, len(draft_tokens) - 1)
              if len(draft_tokens) <= SHORT_SENTENCE_TOKENS
              else MAX_CHANGED_FRACTION * len(draft_tokens))
    if changed > budget:
        return CorrectionPlan(
            [], [f"rewrite refused: {changed} of {len(draft_tokens)} tokens changed"],
            changed, False)

    edits: List[Edit] = []
    for _tag, i1, i2, j1, j2 in opcodes:
        # A repair changes words *inside* a sentence.  A pure insertion or a
        # pure deletion at either end is the judge re-bracketing the utterance
        # -- dragging in the next sentence ("Yeah, not big enough." ->
        # "Yeah, not big enough. Too small.") or lopping off a leading clause.
        # Both produce plausible-looking text that is not what was said, so
        # they are refused and become escalations instead.
        at_boundary = i1 == 0 or i2 >= len(draft_tokens)
        if at_boundary and (i2 == i1 or j2 == j1):
            refusals.append(
                "boundary insertion/deletion refused: the correction adds or "
                "drops words at the edge of the sentence")
            continue

        if i2 > i1:
            local_start = draft_tokens[i1][1]
            local_end = draft_tokens[i2 - 1][2]
        elif draft_tokens:
            anchor = draft_tokens[min(i1, len(draft_tokens) - 1)]
            local_start = local_end = anchor[1] if i1 < len(draft_tokens) else anchor[2]
        else:  # pragma: no cover - a sentence with no words
            local_start = local_end = 0

        if j2 > j1:
            replacement = correction[corr_tokens[j1][1]:corr_tokens[j2 - 1][2]]
            if i2 == i1:
                # An interior insertion splices into a zero-width slot; without
                # padding it fuses onto the neighbouring word.
                replacement = replacement + " "
        else:
            replacement = ""

        before_text = draft_sentence[local_start:local_end]
        if is_register_smoothing(before_text, replacement):
            refusals.append(
                f'register smoothing refused: "{before_text}" -> '
                f'"{replacement.strip()}" formalises casual speech')
            continue
        if degrades_casing(before_text, replacement):
            refusals.append(
                f'casing refused: "{before_text}" -> "{replacement.strip()}" '
                'imports the lowercase witness\'s style')
            continue
        if breaks_entity_name(before_text, replacement, roster_names):
            refusals.append(
                f'entity refused: "{before_text}" -> "{replacement.strip()}" '
                'rewrites a canonical name out of the roster')
            continue

        abs_start = sentence_start_char + local_start
        abs_end = sentence_start_char + local_end
        owners = [s for s in segment_spans
                  if s.start_char <= abs_start and s.end_char >= max(abs_end, abs_start)]
        if len(owners) != 1:
            refusals.append(
                f'span "{draft_sentence[local_start:local_end]}" straddles '
                f'{len(owners)} segments; not applied')
            continue
        owner = owners[0]
        edits.append(Edit(segment_index=owner.segment_index,
                          start_char=abs_start - owner.start_char,
                          end_char=abs_end - owner.start_char,
                          replacement=replacement,
                          before=draft_sentence[local_start:local_end]))

    # All or nothing. The judge proposed one coherent sentence; applying the
    # half of it that passed the guards yields text nobody proposed, which
    # fails the design's own test that a ruling "must yield a sentence that
    # reads as something a human actually said". A partly-refused correction
    # is a question for the human, not a licence to write part of it.
    return CorrectionPlan(edits, refusals, changed, bool(edits) and not refusals)


def apply_edits(segment_text: str, edits: Sequence[Edit]) -> str:
    """Apply this segment's edits, right to left, and tidy the whitespace."""
    text = segment_text
    for edit in sorted(edits, key=lambda e: e.start_char, reverse=True):
        text = text[:edit.start_char] + edit.replacement + text[edit.end_char:]
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([,.!?;:])", r"\1", text)


def group_edits(edits: Sequence[Edit]) -> Dict[int, List[Edit]]:
    grouped: Dict[int, List[Edit]] = {}
    for edit in edits:
        grouped.setdefault(edit.segment_index, []).append(edit)
    return grouped

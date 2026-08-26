"""Word-level disagreement flags and sentence selection.

Adapted from ``tools/tournament/build_packets.py`` (which computed flags over a
hand-picked 40-second passage) for production use over a whole video.  Two
changes matter:

* the tournament threw away character positions -- it only ever needed to
  *print* a flag.  Here a flag has to be attributed back to the sentence that
  contains it, so :func:`tokenize` keeps ``(token, start_char, end_char)``.
* the tournament's pivot text was a single joined excerpt.  Here the draft is
  the whole video, so witnesses are aligned in time windows first; a
  ``SequenceMatcher`` over 5 000 tokens against a witness that drifts would
  produce garbage opcodes.

Nothing in this module touches the network, the GPU or the database.

Normalisation is deliberately identical to ASR_SHOWDOWN section 7b (and to the
tournament), so a flag here means the same thing a flag meant in the results
grid: a disagreement that survives lowercasing, punctuation stripping and
filler removal.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Dict, List, Sequence, Tuple

# ASR_SHOWDOWN section 7b.
FILLERS = {"uh", "um", "mm", "hmm", "mmhmm", "ah", "er", "eh", "oh"}

#: faster-whisper word probability below which a word is "self-reported low
#: confidence".  Same threshold the tournament packets used.
LOW_CONFIDENCE_THRESHOLD = 0.55

#: Witnesses are compared inside time windows rather than end to end.  60 s is
#: long enough that a sentence is never split across two windows in practice
#: and short enough that a drifting witness cannot align to the wrong minute.
DEFAULT_WINDOW_SECONDS = 60.0

_WORD_RE = re.compile(r"[A-Za-z0-9']+")

#: Colloquial forms and the standard-English renderings of them.  Two ASR
#: engines disagreeing across this table have not heard different words; they
#: have made different transcription-style choices, and on this channel the
#: colloquial one is right.  Used twice: to stop a disagreement here summoning
#: the judge (:func:`is_substantive`), and to stop the judge's "correction"
#: being written if it asks for one anyway
#: (``scripts.pipeline.corrections.is_register_smoothing``).
CONTRACTION_EXPANSIONS = {
    "wanna": {"want to", "want a"},
    "gonna": {"going to"},
    "gotta": {"got to", "have to"},
    "kinda": {"kind of"},
    "sorta": {"sort of"},
    "lotta": {"lot of"},
    "outta": {"out of"},
    "gimme": {"give me"},
    "lemme": {"let me"},
    "dunno": {"do not know", "don't know"},
    "cuz": {"because"},
    "cause": {"because"},
    "em": {"them"},
    "ya": {"you"},
    "yeah": {"yes"},
    "yep": {"yes"},
    "nah": {"no"},
    "nope": {"no"},
    "ain't": {"is not", "isn't", "are not", "aren't", "am not"},
    "til": {"until"},
    "'til": {"until"},
}

#: A pure insertion or deletion longer than this is witness *misalignment*,
#: not a dropped phrase.  Measured on a 2-hour video: 174 of 831 flags were
#: one witness having 3+ words the other had nothing for, and the samples are
#: unmistakable -- e.g. YouTube carrying "was so long it was getting tangled
#: at every single tree got here" against nothing in the draft.  Short gaps
#: are kept, because the tournament's single strongest result (recovering
#: "Say hi" from witnesses 2+3 in the dog-chaos passage) lives exactly there.
MAX_GAP_WORDS = 2


def is_register_variant(left: str, right: str) -> bool:
    """True when two readings differ only in colloquial vs standard form."""
    left = re.sub(r"\s+", " ", (left or "").strip().lower())
    right = re.sub(r"\s+", " ", (right or "").strip().lower())
    if not left or not right or left == right:
        return left == right and bool(left)
    return (right in CONTRACTION_EXPANSIONS.get(left, ())
            or left in CONTRACTION_EXPANSIONS.get(right, ()))


def is_substantive(flag: dict) -> bool:
    """Is this disagreement worth waking the judge for?

    Substantive means the two witnesses heard the *same stretch of audio* and
    rendered it as different words.  Three kinds of flag are not that:

    * **Register variants** -- ``"going to"`` vs ``"gonna"``.  147 of 831 flags
      on the measured video, and by far the commonest single pattern.  The
      channel's speaker says "gonna"; that is not an error to adjudicate.
    * **Long one-sided gaps** -- one witness has 3+ words the other has none
      for.  That is alignment drift between two independently-segmented
      transcripts, not a dropped phrase.
    * **Empty flags** -- nothing on either side.
    """
    draft = "" if flag.get("span") in (None, "(nothing)") else flag["span"].strip()
    alternatives = [v for v in (flag.get("alternatives") or {}).values()
                    if v and v != "(nothing)"]
    if not draft and not alternatives:
        return False
    for alternative in alternatives or [""]:
        if draft and alternative:
            if is_register_variant(draft, alternative):
                continue          # this witness adds nothing; try the next
            return True
        else:                     # one-sided: a gap
            words = len((draft or alternative).split())
            if words <= MAX_GAP_WORDS:
                return True
    return False


def substantive_flags(flags: Sequence[dict]) -> List[dict]:
    return [f for f in flags if is_substantive(f)]


def normalise_word(word: str) -> str:
    """Lowercase, expand the two contractions the showdown expanded, strip."""
    word = word.lower().strip("'")
    return word


def normalise_text(text: str) -> str:
    return text.lower().replace("gimme", "give me").replace("'em", "them")


def tokenize(text: str) -> List[Tuple[str, int, int]]:
    """Return ``[(normalised_token, start_char, end_char), ...]``.

    Fillers are dropped (they are never evidence of an error), but the
    character offsets refer to the *original* string so a token index can
    always be mapped back to the draft text.
    """
    lowered = normalise_text(text)
    # normalise_text can change the length ("gimme" -> "give me"), which would
    # invalidate the offsets.  Only use the cheap in-place lowering for offset
    # purposes and apply the expansions per token instead.
    del lowered
    out: List[Tuple[str, int, int]] = []
    for match in _WORD_RE.finditer(text):
        raw = match.group()
        token = normalise_word(raw)
        if not token or token in FILLERS:
            continue
        if token == "gimme":
            # one source token, two normalised tokens -- both point at the
            # same span, which is what a downstream char lookup wants.
            out.append(("give", match.start(), match.end()))
            out.append(("me", match.start(), match.end()))
            continue
        out.append((token, match.start(), match.end()))
    return out


def tokens_only(text: str) -> List[str]:
    return [t for t, _s, _e in tokenize(text)]


# --------------------------------------------------------------------------
# windows
# --------------------------------------------------------------------------

def segments_in_window(segments: Sequence[dict], start: float, end: float) -> List[dict]:
    """Segments overlapping ``[start, end)``.

    Accepts either Whisper segments (``start``/``end``) or wiki
    ``transcript_segments`` rows (``start_seconds``/``duration_seconds``).
    """
    out = []
    for seg in segments:
        s = seg.get("start")
        if s is None:
            s = seg.get("start_seconds") or 0.0
        e = seg.get("end")
        if e is None:
            e = float(s) + float(seg.get("duration_seconds") or 0.0)
        if float(e) > start and float(s) < end:
            out.append(seg)
    return out


def segment_text(seg: dict) -> str:
    return (seg.get("text") or "").strip()


def join_segments(segments: Sequence[dict]) -> str:
    return " ".join(segment_text(s) for s in segments if segment_text(s)).strip()


# --------------------------------------------------------------------------
# disagreement flags
# --------------------------------------------------------------------------

def disagreement_flags(draft_text: str,
                       witness_texts: Dict[str, str],
                       char_offset: int = 0) -> List[dict]:
    """Spans where a witness disagrees with the Whisper draft.

    ``draft_text`` is the pivot.  Returns one dict per disputed span::

        {"span": "captain tea truck",       # as the draft reads
         "context": "...",                  # +/-3 tokens around it
         "start_char": 412, "end_char": 429,
         "alternatives": {"youtube": "captain trot"}}

    ``start_char``/``end_char`` are offsets into ``draft_text`` shifted by
    ``char_offset`` -- pass the window's offset within the full transcript and
    the flags come back already positioned in the whole video.

    An insertion by a witness (nothing in the draft) has a zero-width span; it
    is kept, because "the other two heard two extra words here" is exactly the
    dog-chaos signal, but it is anchored at the insertion point so it still
    lands in a sentence.
    """
    draft_tokens = tokenize(draft_text)
    if not draft_tokens or not witness_texts:
        return []
    base = [t for t, _s, _e in draft_tokens]

    flags: Dict[Tuple[int, int], dict] = {}
    for name, text in witness_texts.items():
        other = tokens_only(text or "")
        if not other:
            continue
        matcher = SequenceMatcher(a=base, b=other, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            lo, hi = max(0, i1 - 3), min(len(base), i2 + 3)
            entry = flags.setdefault((i1, i2), {
                "span": " ".join(base[i1:i2]),
                "context": " ".join(base[lo:hi]),
                "token_range": [i1, i2],
                "alternatives": {},
            })
            entry["alternatives"][name] = " ".join(other[j1:j2])

    out = []
    for (i1, i2), entry in sorted(flags.items()):
        if i2 > i1:
            start_char = draft_tokens[i1][1]
            end_char = draft_tokens[i2 - 1][2]
        else:
            # pure insertion: anchor at the token boundary
            anchor = draft_tokens[min(i1, len(draft_tokens) - 1)]
            start_char = end_char = anchor[1]
        entry["span"] = entry["span"] or "(nothing)"
        entry["alternatives"] = {k: (v or "(nothing)")
                                 for k, v in entry["alternatives"].items()}
        entry["start_char"] = start_char + char_offset
        entry["end_char"] = end_char + char_offset
        out.append(entry)
    return out


def low_confidence_words(segments: Sequence[dict],
                         threshold: float = LOW_CONFIDENCE_THRESHOLD) -> List[dict]:
    """Whisper words whose self-reported probability is below ``threshold``.

    Word dicts are faster-whisper's shape as written by ``run_whisper``:
    ``{"w": " word", "s": 12.3, "e": 12.6, "p": 0.41}``.
    """
    lows = []
    for seg in segments:
        for word in seg.get("words") or []:
            prob = word.get("p")
            if prob is None or prob >= threshold:
                continue
            lows.append({
                "word": (word.get("w") or "").strip(),
                "t": round(float(word.get("s") or 0.0), 2),
                "p": round(float(prob), 3),
            })
    return sorted(lows, key=lambda x: x["p"])


# --------------------------------------------------------------------------
# sentence selection
# --------------------------------------------------------------------------

def select_sentences(sentences: Sequence["object"],
                     flags: Sequence[dict],
                     lows: Sequence[dict],
                     require_flag: bool = True) -> List[int]:
    """Indices of the sentences that must go to the judge.

    A sentence is selected when it contains a **substantive witness
    disagreement flag** — a place where Whisper and the YouTube ASR actually
    heard different words, after register variants and long one-sided
    alignment gaps are discounted (:func:`is_substantive`).  Everything else
    is context: the tournament showed that handing a judge unflagged text is
    how you get false corrections (`bare` packets: WER +0.176), so unflagged
    sentences are never put up for judgement.

    ``require_flag=False`` restores the older, looser bar where a
    low-confidence Whisper word was enough on its own.  That bar selected
    60–66 % of every video's sentences and put the corpus cost at ~100 GPU
    hours; low confidence turns out to mark *disfluency* far more often than
    error, which is the one thing the tournament proved is reliably **not**
    an error.  Low-confidence words still ride into the packet as supporting
    evidence for a sentence a flag already selected — they just no longer
    summon the judge by themselves.

    ``sentences`` are :class:`scripts.pipeline.sentences.Sentence` objects (or
    anything with ``start_char``/``end_char``/``start``/``end``).
    """
    triggers = substantive_flags(flags)
    selected = set()
    for index, sentence in enumerate(sentences):
        s_start = getattr(sentence, "start_char")
        s_end = getattr(sentence, "end_char")
        for flag in triggers:
            f_start = flag.get("start_char")
            f_end = flag.get("end_char", f_start)
            if f_start is None:
                continue
            # zero-width insertions count as inside when they touch the range
            if f_start < s_end and max(f_end, f_start + 1) > s_start:
                selected.add(index)
                break
        else:
            if require_flag:
                continue
            t0 = getattr(sentence, "start", None)
            t1 = getattr(sentence, "end", None)
            if t0 is None or t1 is None:
                continue
            for low in lows:
                if t0 <= low["t"] <= t1:
                    selected.add(index)
                    break
    return sorted(selected)


def flags_for_sentence(sentence, flags: Sequence[dict]) -> List[dict]:
    """The subset of ``flags`` whose span falls inside ``sentence``."""
    out = []
    for flag in flags:
        f_start = flag.get("start_char")
        if f_start is None:
            continue
        f_end = max(flag.get("end_char", f_start), f_start + 1)
        if f_start < sentence.end_char and f_end > sentence.start_char:
            out.append(flag)
    return out


def lows_for_sentence(sentence, lows: Sequence[dict]) -> List[dict]:
    return [low for low in lows if sentence.start <= low["t"] <= sentence.end]


def group_runs(indices: Sequence[int], max_gap: int = 8,
               max_size: int = 12) -> List[List[int]]:
    """Group selected sentence indices into packet-sized runs.

    Nearby flagged sentences travel together so the judge sees them in their
    own context, and — this is the cost lever — so that one model call covers
    several of them.

    A caution learned by measuring rather than reasoning: **packet count is
    not the cost.**  Consolidating 269 packets into 102 looked like a 2.6x
    saving on paper and delivered nothing like it — judge time scales with the
    *content* reasoned over, not with the number of calls, so bigger packets
    simply take proportionally longer (27 s each at 3/8, 54 s each at 8/12).
    The honest unit is **judge-seconds per audio-hour**, and the real saving
    came from raising the selection bar, not from regrouping.

    Grouping still matters for a different reason: fewer calls means the fixed
    ~8 k-character preamble (style card + roster + register guard) is paid
    fewer times, and it keeps related flags in front of the judge together.

    8/12 is the largest grouping whose worst-case prompt (31 k characters)
    still fits the judge's context with the answer budget intact; anything
    bigger needs ``num_ctx`` raised.  :func:`scripts.pipeline.judge_batch.prepare`
    splits any packet that overruns anyway, so this is a target rather than a
    guarantee.
    """
    groups: List[List[int]] = []
    current: List[int] = []
    for index in indices:
        if current and (index - current[-1] > max_gap or len(current) >= max_size):
            groups.append(current)
            current = []
        current.append(index)
    if current:
        groups.append(current)
    return groups

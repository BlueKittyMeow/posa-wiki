"""Transcript pipeline: flags, sentence selection, verdict application, queue.

Everything here runs against fixture data with the Whisper and judge outputs
mocked, so the suite needs no GPU, no network and no MarshLair.  The point is
to pin the parts that were previously only checked by eye -- TOURNAMENT_RESULTS
records three scorer bugs found by inspection rather than by test, including a
correction-applier that scrambled text when a model emitted a one-word span.
Those failure modes get explicit tests here.
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pipeline import flags as flagmod
from scripts.pipeline import packets as packetmod
from scripts.pipeline.corrections import apply_edits, group_edits, plan_correction
from scripts.pipeline.sentences import sentences_from_segments
from services import review_service


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------

def _word(text, start, prob=0.95):
    return {"w": text, "s": start, "e": start + 0.3, "p": prob}


@pytest.fixture
def whisper_payload():
    """A three-segment Whisper draft with one low-confidence word.

    Modelled on the shape ``scripts/pipeline/whisper_worker.py`` writes.
    """
    return {
        "video_id": "vidTEST0001",
        "segments": [
            {"start": 10.0, "end": 13.0,
             "text": "We are targeting some crappie today.",
             "words": [_word(" We", 10.0), _word(" are", 10.3),
                       _word(" targeting", 10.6), _word(" some", 11.0),
                       _word(" crappie", 11.3, 0.41), _word(" today", 11.9)]},
            {"start": 13.0, "end": 16.0,
             "text": "Say hi, Funk.",
             "words": [_word(" Say", 13.0), _word(" hi", 13.3),
                       _word(" Funk", 13.7, 0.32)]},
            {"start": 16.0, "end": 19.0,
             "text": "Captain Tea Truck caught seven of them.",
             "words": [_word(" Captain", 16.0), _word(" Tea", 16.4, 0.30),
                       _word(" Truck", 16.8, 0.28), _word(" caught", 17.2),
                       _word(" seven", 17.6), _word(" of", 18.0),
                       _word(" them", 18.2)]},
        ],
        "meta": {"engine": "faster-whisper large-v3 float16"},
    }


@pytest.fixture
def youtube_segments():
    """The second witness, disagreeing in two places."""
    return [
        {"start_seconds": 10.0, "duration_seconds": 3.0,
         "text": "we are targeting some crappy today"},
        {"start_seconds": 13.0, "duration_seconds": 3.0,
         "text": "say hi punk"},
        {"start_seconds": 16.0, "duration_seconds": 3.0,
         "text": "captain trot caught seven of them"},
    ]


@pytest.fixture
def video_meta():
    return {"title": "Crap-Pie - The Unsuccessful Fishing Show",
            "description": "Fishing with Monty."}


@pytest.fixture
def roster():
    return packetmod.build_roster(
        people=[{"name": "Matthew Posa",
                 "aliases": ["Captain Teeny Trout", "Teeny Trout"]},
                {"name": "Funk", "aliases": []}],
        dogs=[{"name": "Monty", "breed": "Golden Retriever"}])


# --------------------------------------------------------------------------
# sentences
# --------------------------------------------------------------------------

def test_sentences_map_back_to_segments(whisper_payload):
    draft, spans, sentences = sentences_from_segments(whisper_payload["segments"])
    assert [s.text for s in sentences] == [
        "We are targeting some crappie today.",
        "Say hi, Funk.",
        "Captain Tea Truck caught seven of them.",
    ]
    # every sentence's char range indexes back into the joined draft exactly
    for sentence in sentences:
        assert draft[sentence.start_char:sentence.end_char] == sentence.text
    assert [s.segment_indices for s in sentences] == [[0], [1], [2]]
    assert sentences[1].start == 13.0 and sentences[1].end == 16.0
    assert len(spans) == 3


def test_sentence_spanning_two_segments():
    segments = [{"start": 0.0, "end": 2.0, "text": "We are targeting"},
                {"start": 2.0, "end": 4.0, "text": "some crappie today."}]
    draft, _spans, sentences = sentences_from_segments(segments)
    assert len(sentences) == 1
    assert sentences[0].segment_indices == [0, 1]
    assert draft == "We are targeting some crappie today."


# --------------------------------------------------------------------------
# flag computation
# --------------------------------------------------------------------------

def test_flags_locate_the_disagreements(whisper_payload, youtube_segments):
    draft, spans, _sentences = sentences_from_segments(whisper_payload["segments"])
    found = packetmod.compute_flags(draft, spans, youtube_segments)
    spans_seen = {f["span"] for f in found}
    assert "crappie" in spans_seen
    assert "funk" in spans_seen
    assert any("tea truck" in s for s in spans_seen)
    for flag in found:
        # a flag's char range must point at the words it claims
        assert flag["span"].split()[0] in draft[flag["start_char"]:
                                                flag["end_char"] + 4].lower()


def test_flags_need_a_second_witness(whisper_payload):
    draft, spans, _sentences = sentences_from_segments(whisper_payload["segments"])
    assert packetmod.compute_flags(draft, spans, []) == []


def test_fillers_never_flag():
    assert flagmod.tokens_only("uh well um yes") == ["well", "yes"]
    found = flagmod.disagreement_flags("Well, uh, yes.", {"youtube": "well yes"})
    assert found == []


def test_low_confidence_words(whisper_payload):
    lows = flagmod.low_confidence_words(whisper_payload["segments"])
    words = {low["word"] for low in lows}
    assert {"crappie", "Funk", "Tea", "Truck"} <= words
    assert lows[0]["p"] <= lows[-1]["p"]      # sorted worst-first


# --------------------------------------------------------------------------
# sentence selection
# --------------------------------------------------------------------------

def test_only_flagged_sentences_are_selected(whisper_payload, youtube_segments):
    draft, spans, sentences = sentences_from_segments(whisper_payload["segments"])
    found = packetmod.compute_flags(draft, spans, youtube_segments)
    lows = flagmod.low_confidence_words(whisper_payload["segments"])
    assert flagmod.select_sentences(sentences, found, lows) == [0, 1, 2]


def test_unflagged_sentences_are_context_only():
    segments = [
        {"start": 0.0, "end": 2.0, "text": "The weather is beautiful.",
         "words": [_word(" The", 0.0), _word(" weather", 0.4),
                   _word(" is", 0.9), _word(" beautiful", 1.2)]},
        {"start": 2.0, "end": 4.0, "text": "Say hi, Funk.",
         "words": [_word(" Say", 2.0), _word(" hi", 2.4), _word(" Funk", 2.8)]},
    ]
    youtube = [{"start_seconds": 0.0, "duration_seconds": 4.0,
                "text": "the weather is beautiful say hi punk"}]
    draft, spans, sentences = sentences_from_segments(segments)
    found = packetmod.compute_flags(draft, spans, youtube)
    lows = flagmod.low_confidence_words(segments)
    selected = flagmod.select_sentences(sentences, found, lows)
    # only the sentence carrying the funk/punk disagreement
    assert selected == [1]


def test_low_confidence_alone_no_longer_summons_the_judge():
    """The raised bar: a witness disagreement is required, not mere doubt.

    Low confidence marks disfluency far more often than error, and the loose
    bar selected 60-66 % of every video (~100 GPU-hours for the corpus).
    """
    segments = [
        {"start": 0.0, "end": 2.0, "text": "The weather is beautiful.",
         "words": [_word(" The", 0.0), _word(" weather", 0.4, 0.20),
                   _word(" is", 0.9), _word(" beautiful", 1.2, 0.18)]},
        {"start": 2.0, "end": 4.0, "text": "Say hi, Funk.",
         "words": [_word(" Say", 2.0), _word(" hi", 2.4), _word(" Funk", 2.8)]},
    ]
    youtube = [{"start_seconds": 0.0, "duration_seconds": 4.0,
                "text": "the weather is beautiful say hi punk"}]
    draft, spans, sentences = sentences_from_segments(segments)
    found = packetmod.compute_flags(draft, spans, youtube)
    lows = flagmod.low_confidence_words(segments)
    assert len(lows) == 2                      # sentence 0 is full of doubt ...
    assert flagmod.select_sentences(sentences, found, lows) == [1]
    # ... and the old bar would have taken it
    assert flagmod.select_sentences(sentences, found, lows,
                                    require_flag=False) == [0, 1]


def test_low_confidence_still_rides_into_the_packet(whisper_payload,
                                                    youtube_segments,
                                                    video_meta, roster):
    """Demoted as a trigger, kept as evidence."""
    draft, spans, sentences = sentences_from_segments(whisper_payload["segments"])
    found = packetmod.compute_flags(draft, spans, youtube_segments)
    lows = flagmod.low_confidence_words(whisper_payload["segments"])
    packet = packetmod.build_packet(video_meta, roster, sentences, [2], found,
                                    lows, youtube_segments, "vid__0000")
    assert packet["whisper_low_confidence"]


def test_group_runs_caps_packet_size():
    # a gap wider than max_gap starts a new packet ...
    assert flagmod.group_runs([0, 1, 2, 10, 11], max_gap=3) == [[0, 1, 2],
                                                               [10, 11]]
    # ... but the production default merges across it, because packets (not
    # flagged sentences) are what a run costs
    assert flagmod.group_runs([0, 1, 2, 10, 11]) == [[0, 1, 2, 10, 11]]
    assert flagmod.group_runs(list(range(8)), max_size=3) == [
        [0, 1, 2], [3, 4, 5], [6, 7]]


# --------------------------------------------------------------------------
# packets
# --------------------------------------------------------------------------

def test_packet_carries_context_and_flags(whisper_payload, youtube_segments,
                                          video_meta, roster):
    draft, spans, sentences = sentences_from_segments(whisper_payload["segments"])
    found = packetmod.compute_flags(draft, spans, youtube_segments)
    lows = flagmod.low_confidence_words(whisper_payload["segments"])
    packet = packetmod.build_packet(video_meta, roster, sentences, [1], found,
                                    lows, youtube_segments, "vid__0000")
    assert packet["witness_set"] == "W+YT"
    assert "Say hi, Funk." in packet["draft_transcript"]
    # context sentences ride along
    assert "crappie" in packet["draft_transcript"]
    assert packet["_sentence_indices"] == [1]
    assert any("funk" in f["whisper_span"] for f in packet["disagreement_flags"])


def test_packet_prompt_uses_the_tournament_builder(whisper_payload,
                                                   youtube_segments,
                                                   video_meta, roster):
    """The production prompt must be the `full` ablation, unchanged."""
    sys.path.insert(0, str(REPO_ROOT / "tools" / "tournament"))
    from judge_prompt import ABLATIONS, build_prompt

    draft, spans, sentences = sentences_from_segments(whisper_payload["segments"])
    found = packetmod.compute_flags(draft, spans, youtube_segments)
    lows = flagmod.low_confidence_words(whisper_payload["segments"])
    packet = packetmod.build_packet(video_meta, roster, sentences, [2], found,
                                    lows, youtube_segments, "vid__0000")
    prompt = build_prompt(packet, **ABLATIONS["full"])
    assert "style card" in prompt
    assert "Captain Teeny Trout" in prompt        # the lexicon that recovers it
    assert "FLAGGED SPANS" in prompt
    assert "JSON array and nothing else" in prompt


# --------------------------------------------------------------------------
# correction planning -- the tournament's applier bugs
# --------------------------------------------------------------------------

def test_one_word_correction_is_a_minimal_edit():
    """The bug that scrambled text: a one-word span must edit one word."""
    segments = [{"start": 0.0, "end": 3.0,
                 "text": "Captain Tea Truck caught seven of them."}]
    _draft, spans, sentences = sentences_from_segments(segments)
    plan = plan_correction(sentences[0].text,
                           "Captain Teeny Trout caught seven of them.",
                           spans, sentences[0].start_char)
    assert plan.applicable
    edited = apply_edits(segments[0]["text"], plan.edits)
    assert edited == "Captain Teeny Trout caught seven of them."


def test_null_correction_is_refused():
    segments = [{"start": 0.0, "end": 2.0, "text": "Say hi, Funk."}]
    _draft, spans, sentences = sentences_from_segments(segments)
    plan = plan_correction(sentences[0].text, "Say hi, Funk.", spans,
                           sentences[0].start_char)
    assert not plan.applicable
    assert plan.is_null
    assert "null correction" in plan.refusals[0]


def test_wholesale_rewrite_is_refused():
    """`gutenberg-12b`'s failure mode: smoothing disfluent speech into prose."""
    segments = [{"start": 0.0, "end": 4.0,
                 "text": "Oh boy oh boy here we go get it get it Monty."}]
    _draft, spans, sentences = sentences_from_segments(segments)
    plan = plan_correction(
        sentences[0].text,
        "Oh my, here we are; go and fetch it, Monty, my good dog.",
        spans, sentences[0].start_char)
    assert not plan.applicable
    assert "rewrite refused" in plan.refusals[0]


def test_correction_across_two_segments_is_refused():
    segments = [{"start": 0.0, "end": 2.0, "text": "Captain Tea"},
                {"start": 2.0, "end": 4.0, "text": "Truck caught seven."}]
    _draft, spans, sentences = sentences_from_segments(segments)
    plan = plan_correction(sentences[0].text,
                           "Captain Teeny Trout caught seven.",
                           spans, sentences[0].start_char)
    assert not plan.applicable
    assert "straddles" in plan.refusals[0]


def test_empty_correction_is_refused():
    segments = [{"start": 0.0, "end": 2.0, "text": "Say hi, Funk."}]
    _draft, spans, sentences = sentences_from_segments(segments)
    plan = plan_correction(sentences[0].text, "   ", spans,
                           sentences[0].start_char)
    assert not plan.applicable


def test_trailing_insertion_is_refused():
    """The judge drags in the next sentence; that is not a repair.

    Caught in the first live run: draft "Yeah, not big enough." came back as
    "Yeah, not big enough. Too small." and the applier wrote
    "Yeah, not big enoughToo small."
    """
    segments = [{"start": 0.0, "end": 2.0, "text": "Yeah, not big enough."}]
    _draft, spans, sentences = sentences_from_segments(segments)
    plan = plan_correction(sentences[0].text, "Yeah, not big enough. Too small.",
                           spans, sentences[0].start_char)
    assert not plan.applicable
    assert "boundary insertion/deletion" in plan.refusals[0]


def test_leading_insertion_is_refused():
    segments = [{"start": 0.0, "end": 2.0, "text": "You're such a little turd."}]
    _draft, spans, sentences = sentences_from_segments(segments)
    plan = plan_correction(sentences[0].text,
                           "Where are we going, Monty? You're such a little turd.",
                           spans, sentences[0].start_char)
    assert not plan.applicable


def test_leading_clause_deletion_is_refused():
    segments = [{"start": 0.0, "end": 4.0,
                 "text": "So the reason we're shoveling is because last time "
                         "I went out with Monty, I did it."}]
    _draft, spans, sentences = sentences_from_segments(segments)
    plan = plan_correction(sentences[0].text,
                           "last time I went out with Monty, I did it.",
                           spans, sentences[0].start_char)
    assert not plan.applicable


def test_short_sentence_total_replacement_is_refused():
    """Live run: "All right, Monty." came back as "monte come on out."."""
    segments = [{"start": 0.0, "end": 2.0, "text": "All right, Monty."}]
    _draft, spans, sentences = sentences_from_segments(segments)
    plan = plan_correction(sentences[0].text, "Monte, come on out.", spans,
                           sentences[0].start_char)
    assert not plan.applicable
    assert "rewrite refused" in plan.refusals[0]


def test_short_sentence_single_word_fix_is_allowed():
    segments = [{"start": 0.0, "end": 2.0, "text": "That's a gal right there."}]
    _draft, spans, sentences = sentences_from_segments(segments)
    plan = plan_correction(sentences[0].text, "That's a gill right there.",
                           spans, sentences[0].start_char)
    assert plan.applicable
    assert apply_edits(segments[0]["text"], plan.edits) == \
        "That's a gill right there."


def test_first_word_substitution_is_still_allowed():
    """Refusing boundary *insertions* must not refuse boundary replacements."""
    segments = [{"start": 0.0, "end": 2.0, "text": "Did you sleep good?"}]
    _draft, spans, sentences = sentences_from_segments(segments)
    plan = plan_correction(sentences[0].text, "Do you sleep good?", spans,
                           sentences[0].start_char)
    assert plan.applicable
    assert apply_edits(segments[0]["text"], plan.edits) == "Do you sleep good?"


def test_interior_insertion_keeps_its_spaces():
    segments = [{"start": 0.0, "end": 2.0, "text": "I'm happy to be the woods."}]
    _draft, spans, sentences = sentences_from_segments(segments)
    plan = plan_correction(sentences[0].text, "I'm happy to be in the woods.",
                           spans, sentences[0].start_char)
    assert plan.applicable
    assert apply_edits(segments[0]["text"], plan.edits) == \
        "I'm happy to be in the woods."


def test_second_ruling_on_one_segment_is_queued_not_applied():
    """Two rulings, one segment: the second would splice at stale offsets.

    The live run produced a three-step cascade -- "All right, Monty." became
    "bags overAll right,." became "monte come on outht,." -- because each plan
    was computed against the original text but applied to the edited text.
    """
    from scripts.pipeline import apply_verdicts

    whisper = {"segments": [
        {"start": 0.0, "end": 3.0,
         "text": "Captain Tea Truck caught seven crappy.", "words": []}]}
    _d, _s, sentences = sentences_from_segments(whisper["segments"])
    verdicts = {"rulings": [
        {"sentence_index": 0, "draft_sentence": sentences[0].text,
         "span": "Tea Truck", "verdict": "correct",
         "correction": "Captain Teeny Trout caught seven crappy.",
         "reasoning": "roster alias", "witness_disagreement": ""},
        {"sentence_index": 0, "draft_sentence": sentences[0].text,
         "span": "crappy", "verdict": "correct",
         "correction": "Captain Tea Truck caught seven crappie.",
         "reasoning": "domain term", "witness_disagreement": ""},
    ]}
    _segments, texts, corrections, queue_items, stats = \
        apply_verdicts.plan_video(whisper, verdicts, auto_apply=True)
    assert texts[0] == "Captain Teeny Trout caught seven crappy."
    assert len(corrections) == 1
    assert stats["applied"] == 1 and stats["refused"] == 1
    assert "already corrected" in queue_items[0]["judge_reasoning"]


def test_contraction_expansion_is_refused():
    """Live run: "wanna cut" was written as "want to cut"."""
    segments = [{"start": 0.0, "end": 3.0,
                 "text": "See, you wanna cut on the bottom side."}]
    _draft, spans, sentences = sentences_from_segments(segments)
    plan = plan_correction(sentences[0].text,
                           "See, you want to cut on the bottom side.",
                           spans, sentences[0].start_char)
    assert not plan.applicable
    assert "register smoothing" in plan.refusals[0]


@pytest.mark.parametrize("before,after", [
    ("gonna", "going to"), ("gotta", "have to"), ("kinda", "kind of"),
    ("gimme", "give me"), ("em", "them"), ("yeah", "yes"),
])
def test_register_smoothing_table(before, after):
    from scripts.pipeline.corrections import is_register_smoothing
    assert is_register_smoothing(before, after)
    assert not is_register_smoothing(before, "something else entirely")


def test_lowercase_splice_from_the_youtube_witness_is_refused():
    """Live run: "Layla's sleeping" came back as "leila's sleeping"."""
    segments = [{"start": 0.0, "end": 3.0,
                 "text": "Seeing as how I didn't get much sleep."}]
    _draft, spans, sentences = sentences_from_segments(segments)
    plan = plan_correction(sentences[0].text,
                           "see is how I didn't get much sleep.",
                           spans, sentences[0].start_char)
    assert not plan.applicable
    assert "casing refused" in plan.refusals[0]


def test_correction_that_destroys_a_roster_name_is_refused():
    segments = [{"start": 0.0, "end": 3.0,
                 "text": "Layla's sleeping under Lucas's cot over there."}]
    _draft, spans, sentences = sentences_from_segments(segments)
    plan = plan_correction(sentences[0].text,
                           "Leila's sleeping under Lucas's cod over there.",
                           spans, sentences[0].start_char,
                           roster_names=["Layla", "Lucas", "Monty", "Rueger"])
    assert not plan.applicable
    assert any("entity refused" in r for r in plan.refusals)


def test_roster_guard_still_allows_recovering_a_name():
    """The lexicon must keep working in the direction it was built for."""
    segments = [{"start": 0.0, "end": 3.0, "text": "Rouger is not here."}]
    _draft, spans, sentences = sentences_from_segments(segments)
    plan = plan_correction(sentences[0].text, "Rueger is not here.", spans,
                           sentences[0].start_char,
                           roster_names=["Rueger", "Layla"])
    assert plan.applicable
    assert apply_edits(segments[0]["text"], plan.edits) == "Rueger is not here."


def test_a_real_word_swap_is_not_register_smoothing():
    from scripts.pipeline.corrections import is_register_smoothing
    assert not is_register_smoothing("gal", "gill")
    assert not is_register_smoothing("Rouger", "Rueger")


def test_judge_prompt_carries_the_register_guard(whisper_payload,
                                                 youtube_segments,
                                                 video_meta, roster):
    sys.path.insert(0, str(REPO_ROOT / "tools" / "tournament"))
    from judge_prompt import ABLATIONS, build_prompt

    from scripts.pipeline.judge_batch import CONTRACTION_GUARD

    draft, spans, sentences = sentences_from_segments(whisper_payload["segments"])
    found = packetmod.compute_flags(draft, spans, youtube_segments)
    lows = flagmod.low_confidence_words(whisper_payload["segments"])
    packet = packetmod.build_packet(video_meta, roster, sentences, [2], found,
                                    lows, youtube_segments, "vid__0000")
    guarded = build_prompt(packet, extra_caution=CONTRACTION_GUARD,
                           **ABLATIONS["full"])
    assert "REGISTER GUARD" in guarded
    assert '"wanna" stays "wanna"' in guarded
    # the guard sits before the output spec, so the JSON instruction stays last
    assert guarded.index("REGISTER GUARD") < guarded.index("OUTPUT FORMAT")
    # and the tournament prompt is unchanged without it
    assert "REGISTER GUARD" not in build_prompt(packet, **ABLATIONS["full"])


def test_group_edits_by_segment():
    segments = [{"start": 0.0, "end": 3.0,
                 "text": "Captain Tea Truck caught seven crappy."}]
    _draft, spans, sentences = sentences_from_segments(segments)
    plan = plan_correction(sentences[0].text,
                           "Captain Teeny Trout caught seven crappie.",
                           spans, sentences[0].start_char)
    grouped = group_edits(plan.edits)
    assert set(grouped) == {0}
    assert apply_edits(segments[0]["text"], grouped[0]) == \
        "Captain Teeny Trout caught seven crappie."


# --------------------------------------------------------------------------
# judge schema discipline + ruling attachment (mocked model)
# --------------------------------------------------------------------------

def _judge_module():
    from scripts.pipeline import judge_batch
    return judge_batch


def test_correct_without_correction_is_demoted():
    judge_batch = _judge_module()
    rulings = [{"span": "crappie", "verdict": "correct", "correction": None},
               {"span": "Funk", "verdict": "confirm", "correction": None}]
    assert len(judge_batch.needs_repair(rulings)) == 1
    assert judge_batch.demote(rulings) == 1
    assert rulings[0]["verdict"] == "escalate"
    assert rulings[0]["_demoted"] == "correct-without-correction"
    assert rulings[1]["verdict"] == "confirm"


def test_attach_ruling_by_span_and_by_correction(whisper_payload):
    judge_batch = _judge_module()
    _draft, _spans, sentences = sentences_from_segments(whisper_payload["segments"])
    by_span = judge_batch.attach_ruling({"span": "Tea Truck"}, sentences)
    assert by_span.index == 2
    by_correction = judge_batch.attach_ruling(
        {"span": "nowhere in the draft",
         "correction": "Say hi, Funk."}, sentences)
    assert by_correction.index == 1
    assert judge_batch.attach_ruling(
        {"span": "zzz", "correction": "completely unrelated words here"},
        sentences) is None


def test_oversized_packets_are_split_not_truncated(monkeypatch, video_meta,
                                                   roster):
    """A packet over the context ceiling is halved until it fits.

    ollama truncates silently, so an overrun would drop the flags at the end
    of the prompt without any error to notice.
    """
    judge_batch = _judge_module()
    # 40 flagged sentences, each long, all adjacent -> one huge group
    segments, youtube = [], []
    for i in range(40):
        start = i * 2.0
        text = ("We are going to talk about the %s crappie and the bluegill "
                "and the whole business of it now." % ("big" if i % 2 else "small"))
        segments.append({"start": start, "end": start + 2.0, "text": text,
                         "words": []})
        youtube.append({"start_seconds": start, "duration_seconds": 2.0,
                        "text": text.lower().replace("crappie", "crappy")})
    whisper = {"segments": segments}

    prepared = judge_batch.prepare("vidBIG", whisper, youtube, video_meta, roster)
    assert prepared["packets"], "expected at least one packet"
    sizes = [len(build_guarded_prompt(p)) for p in prepared["packets"]]
    assert max(sizes) <= judge_batch.MAX_PROMPT_CHARS
    # and nothing was dropped: every selected sentence is still covered
    covered = {i for p in prepared["packets"] for i in p["_sentence_indices"]}
    assert covered == set(prepared["selected"])


def build_guarded_prompt(packet):
    sys.path.insert(0, str(REPO_ROOT / "tools" / "tournament"))
    from judge_prompt import ABLATIONS, build_prompt

    from scripts.pipeline.judge_batch import CONTRACTION_GUARD
    return build_prompt(packet, extra_caution=CONTRACTION_GUARD,
                        **ABLATIONS["full"])


def test_judge_video_end_to_end_with_a_mocked_model(
        monkeypatch, whisper_payload, youtube_segments, video_meta, roster):
    judge_batch = _judge_module()
    monkeypatch.setattr(judge_batch, "load_whisper", lambda vid, **kw: whisper_payload)
    monkeypatch.setattr(judge_batch, "load_youtube_segments", lambda vid: youtube_segments)
    monkeypatch.setattr(judge_batch, "load_video_meta", lambda vid: video_meta)
    monkeypatch.setattr(judge_batch, "load_roster", lambda: roster)

    def fake_model(prompt):
        return json.dumps([
            {"span": "Tea Truck", "verdict": "correct",
             "correction": "Captain Teeny Trout caught seven of them.",
             "reasoning": "matches Matthew Posa's alias in the roster"},
            {"span": "crappie", "verdict": "escalate", "correction": None,
             "reasoning": "the title suggests a pun; a human should listen"},
            {"span": "Funk", "verdict": "confirm", "correction": None,
             "reasoning": "Funk is a person in the roster"},
        ])

    verdicts = judge_batch.judge_video("vidTEST0001", generate=fake_model)
    kinds = {r["verdict"] for r in verdicts["rulings"]}
    assert kinds == {"correct", "escalate", "confirm"}
    assert verdicts["witness_set"] == "W+YT"
    assert verdicts["stats"]["correct"] == 1
    assert verdicts["stats"]["escalate"] == 1
    correct = next(r for r in verdicts["rulings"] if r["verdict"] == "correct")
    assert correct["draft_sentence"] == "Captain Tea Truck caught seven of them."
    assert correct["witness_disagreement"]


def test_ungrounded_rulings_are_dropped(monkeypatch, video_meta, roster):
    """A ruling on a sentence with no flag and no low-confidence word is noise.

    TOURNAMENT_RESULTS: 71 escalations, 2 of them on a genuinely hard span.
    """
    judge_batch = _judge_module()
    whisper = {"segments": [
        {"start": 0.0, "end": 2.0, "text": "The weather is beautiful.",
         "words": [_word(" The", 0.0), _word(" weather", 0.4),
                   _word(" is", 0.9), _word(" beautiful", 1.2)]},
        {"start": 2.0, "end": 4.0, "text": "Say hi, Funk.",
         "words": [_word(" Say", 2.0), _word(" hi", 2.4), _word(" Funk", 2.8)]},
    ]}
    youtube = [{"start_seconds": 0.0, "duration_seconds": 4.0,
                "text": "the weather is beautiful say hi punk"}]
    monkeypatch.setattr(judge_batch, "load_whisper", lambda vid, **kw: whisper)
    monkeypatch.setattr(judge_batch, "load_youtube_segments", lambda vid: youtube)
    monkeypatch.setattr(judge_batch, "load_video_meta", lambda vid: video_meta)
    monkeypatch.setattr(judge_batch, "load_roster", lambda: roster)

    verdicts = judge_batch.judge_video("vidTEST0001", generate=lambda p: json.dumps([
        {"span": "beautiful", "verdict": "escalate", "correction": None,
         "reasoning": "sounds odd"},
        {"span": "Funk", "verdict": "escalate", "correction": None,
         "reasoning": "witnesses disagree"},
    ]))
    assert verdicts["stats"]["dropped_ungrounded"] == 1
    assert [r["draft_sentence"] for r in verdicts["rulings"]] == ["Say hi, Funk."]


def test_repair_reask_happens_once(monkeypatch, whisper_payload,
                                   youtube_segments, video_meta, roster):
    judge_batch = _judge_module()
    monkeypatch.setattr(judge_batch, "load_whisper", lambda vid, **kw: whisper_payload)
    monkeypatch.setattr(judge_batch, "load_youtube_segments", lambda vid: youtube_segments)
    monkeypatch.setattr(judge_batch, "load_video_meta", lambda vid: video_meta)
    monkeypatch.setattr(judge_batch, "load_roster", lambda: roster)

    calls = []

    def flaky(prompt):
        calls.append(prompt)
        if "REPAIR INSTRUCTION" in prompt:
            return json.dumps([{"span": "Tea Truck", "verdict": "correct",
                                "correction": "Captain Teeny Trout caught "
                                              "seven of them.",
                                "reasoning": "roster alias"}])
        return json.dumps([{"span": "Tea Truck", "verdict": "correct",
                            "correction": None, "reasoning": "wrong"}])

    verdicts = judge_batch.judge_video("vidTEST0001", generate=flaky)
    assert verdicts["stats"]["repairs"] >= 1
    assert any("REPAIR INSTRUCTION" in c for c in calls)
    assert verdicts["stats"]["correct"] >= 1


# --------------------------------------------------------------------------
# apply_verdicts
# --------------------------------------------------------------------------

def _verdicts_for(whisper_payload):
    _draft, _spans, sentences = sentences_from_segments(whisper_payload["segments"])
    return {
        "video_id": "vidTEST0001",
        "judge": "mistral-small3.2:24b",
        "stats": {},
        "rulings": [
            {"sentence_index": 2, "start_seconds": 16.0, "end_seconds": 19.0,
             "draft_sentence": sentences[2].text, "span": "Tea Truck",
             "verdict": "correct",
             "correction": "Captain Teeny Trout caught seven of them.",
             "reasoning": "roster alias",
             "witness_disagreement": 'draft "tea truck" vs youtube heard "trot"'},
            {"sentence_index": 0, "start_seconds": 10.0, "end_seconds": 13.0,
             "draft_sentence": sentences[0].text, "span": "crappie",
             "verdict": "escalate", "correction": None,
             "reasoning": "the title suggests a pun",
             "witness_disagreement": 'draft "crappie" vs youtube heard "crappy"'},
            {"sentence_index": 1, "start_seconds": 13.0, "end_seconds": 16.0,
             "draft_sentence": sentences[1].text, "span": "Funk",
             "verdict": "confirm", "correction": None,
             "reasoning": "Funk is a person", "witness_disagreement": ""},
        ],
    }


def test_plan_video_splits_corrections_from_escalations(whisper_payload):
    from scripts.pipeline import apply_verdicts

    verdicts = _verdicts_for(whisper_payload)
    segments, texts, corrections, queue_items, stats = \
        apply_verdicts.plan_video(whisper_payload, verdicts, auto_apply=True)
    assert len(segments) == 3
    assert texts[2] == "Captain Teeny Trout caught seven of them."
    assert texts[0] == "We are targeting some crappie today."   # untouched
    assert stats == {"applied": 1, "refused": 0, "escalated": 1,
                     "confirmed": 1, "unmatched": 0, "proposed": 0}
    assert len(corrections) == 1
    assert corrections[0]["before_text"].startswith("Captain Tea Truck")
    assert len(queue_items) == 1
    assert queue_items[0]["draft_sentence"].startswith("We are targeting")


def test_propose_only_is_the_default(whisper_payload):
    """Corrections are candidates, not writes, unless --auto-apply is passed.

    Measured over three whole videos: of the corrections that survived every
    structural guard, most still made the transcript worse. The guards catch a
    pathological shape, not a wrong answer.
    """
    from scripts.pipeline import apply_verdicts

    assert apply_verdicts.AUTO_APPLY_DEFAULT is False
    verdicts = _verdicts_for(whisper_payload)
    _segments, texts, corrections, queue_items, stats = \
        apply_verdicts.plan_video(whisper_payload, verdicts)
    # the draft is untouched ...
    assert texts[2] == "Captain Tea Truck caught seven of them."
    assert corrections == []
    assert stats["applied"] == 0 and stats["proposed"] == 1
    # ... and the judge's reading reaches the human with the proposal attached
    proposed = [q for q in queue_items if q["proposed_correction"]]
    assert proposed[0]["proposed_correction"] == \
        "Captain Teeny Trout caught seven of them."
    # a clean proposal is not reported as a refusal
    assert stats["refused"] == 0
    assert "applier:" not in (proposed[0]["judge_reasoning"] or "")


def test_refused_correction_becomes_an_escalation(whisper_payload):
    from scripts.pipeline import apply_verdicts

    verdicts = _verdicts_for(whisper_payload)
    verdicts["rulings"][0]["correction"] = (
        "The captain, a fine gentleman indeed, did land a full seven fish.")
    _segments, texts, corrections, queue_items, stats = \
        apply_verdicts.plan_video(whisper_payload, verdicts, auto_apply=True)
    assert texts[2] == "Captain Tea Truck caught seven of them."   # untouched
    assert corrections == []
    assert stats["refused"] == 1
    assert stats["escalated"] == 2
    refused = [q for q in queue_items if "applier:" in (q["judge_reasoning"] or "")]
    assert refused and "rewrite refused" in refused[0]["judge_reasoning"]
    # a refused correction still reaches the human, with the proposal attached
    assert refused[0]["proposed_correction"]


def test_item_id_is_stable_and_video_scoped():
    from scripts.pipeline import apply_verdicts

    first = apply_verdicts.item_id_for("abc", 10.0, "Say hi, Funk.", "Funk")
    again = apply_verdicts.item_id_for("abc", 10.0, "Say hi, Funk.", "Funk")
    other = apply_verdicts.item_id_for("xyz", 10.0, "Say hi, Funk.", "Funk")
    assert first == again and first != other
    assert first.startswith("abc:")


# --------------------------------------------------------------------------
# database round-trip: apply -> search preference -> review queue
# --------------------------------------------------------------------------

@pytest.fixture
def pipeline_db(tmp_path, whisper_payload):
    """A throwaway DB with one video, its YouTube segments, and the schema."""
    from scripts.pipeline import apply_verdicts

    path = tmp_path / "pipeline.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE videos (video_id VARCHAR PRIMARY KEY, title TEXT, "
        " description TEXT, upload_date TEXT, thumbnail_url TEXT);")
    conn.executescript(
        (REPO_ROOT / "migrations" / "010_create_transcripts.sql").read_text())
    apply_verdicts.ensure_schema(conn, quiet=True)
    conn.execute("INSERT INTO videos VALUES ('vidTEST0001', 'Crap-Pie', "
                 "'desc', '2021-01-01', 'http://thumb')")
    for seg in [(10.0, 3.0, "we are targeting some crappy today"),
                (13.0, 3.0, "say hi punk"),
                (16.0, 3.0, "captain trot caught seven of them")]:
        conn.execute("INSERT INTO transcript_segments "
                     "(video_id, start_seconds, duration_seconds, text, source) "
                     "VALUES ('vidTEST0001', ?, ?, ?, 'youtube-asr-vtt')", seg)
    conn.commit()
    return conn


def test_apply_video_writes_segments_corrections_and_queue(pipeline_db,
                                                           whisper_payload):
    from scripts.pipeline import apply_verdicts

    conn = pipeline_db
    verdicts = _verdicts_for(whisper_payload)
    stats = apply_verdicts.apply_video(conn, "vidTEST0001", whisper_payload,
                                       verdicts, "judge:mistral-small3.2:24b",
                                       quiet=True, auto_apply=True)
    conn.commit()

    whisper_rows = conn.execute(
        "SELECT text FROM transcript_segments WHERE video_id = 'vidTEST0001' "
        "AND source = 'whisper-large-v3' ORDER BY start_seconds").fetchall()
    assert [r["text"] for r in whisper_rows] == [
        "We are targeting some crappie today.",
        "Say hi, Funk.",
        "Captain Teeny Trout caught seven of them.",
    ]
    # the YouTube witness rows are still there -- nothing is ever deleted
    assert conn.execute(
        "SELECT COUNT(*) FROM transcript_segments WHERE video_id = 'vidTEST0001' "
        "AND source = 'youtube-asr-vtt'").fetchone()[0] == 3

    correction = conn.execute("SELECT * FROM transcript_corrections").fetchone()
    assert correction["before_text"].startswith("Captain Tea Truck")
    assert correction["provenance"] == "judge:mistral-small3.2:24b"

    queued = conn.execute(
        "SELECT * FROM transcript_review_queue WHERE status = 'open'").fetchall()
    assert len(queued) == 1
    assert queued[0]["draft_sentence"].startswith("We are targeting")
    assert queued[0]["proposed_correction"] is None

    status = conn.execute("SELECT * FROM transcript_status").fetchone()
    assert status["whisper_status"] == "ingested"
    assert status["judge_status"] == "judged"
    assert status["corrections_applied"] == 1
    assert status["escalations_queued"] == 1
    assert stats["segments"] == 3


def test_apply_video_is_idempotent(pipeline_db, whisper_payload):
    from scripts.pipeline import apply_verdicts

    conn = pipeline_db
    verdicts = _verdicts_for(whisper_payload)
    for _ in range(2):
        apply_verdicts.apply_video(conn, "vidTEST0001", whisper_payload,
                                   verdicts, "judge:test", quiet=True, auto_apply=True)
    conn.commit()
    assert conn.execute(
        "SELECT COUNT(*) FROM transcript_segments "
        "WHERE source = 'whisper-large-v3'").fetchone()[0] == 3
    assert conn.execute(
        "SELECT COUNT(*) FROM transcript_review_queue").fetchone()[0] == 1


def test_redo_clears_stale_rows_but_keeps_human_decisions(pipeline_db,
                                                          whisper_payload):
    """A re-run must not leave the previous run's rows behind — or eat Lara's."""
    from scripts.pipeline import apply_verdicts

    conn = pipeline_db
    apply_verdicts.apply_video(conn, "vidTEST0001", whisper_payload,
                               _verdicts_for(whisper_payload), "judge:test",
                               quiet=True, auto_apply=True)
    conn.commit()
    # Lara decides one of them, and her decision writes a correction
    queue = review_service.get_queue("transcripts")
    decided = queue.items(conn)[0]
    queue.reject(conn, {"item_id": decided.item_id})
    conn.execute(
        "INSERT INTO transcript_corrections (video_id, before_text, after_text, "
        "provenance, applied_at) VALUES ('vidTEST0001', 'a', 'b', "
        "'human:web-review', '2026-08-26')")
    conn.commit()

    apply_verdicts.apply_video(conn, "vidTEST0001", whisper_payload,
                               _verdicts_for(whisper_payload), "judge:test",
                               quiet=True, redo=True, auto_apply=True)
    conn.commit()

    # judge corrections replaced, not accumulated
    assert conn.execute(
        "SELECT COUNT(*) FROM transcript_corrections "
        "WHERE provenance LIKE 'judge:%'").fetchone()[0] == 1
    # the human's correction survives
    assert conn.execute(
        "SELECT COUNT(*) FROM transcript_corrections "
        "WHERE provenance = 'human:web-review'").fetchone()[0] == 1
    # the decided queue row survives; it is not asked again
    assert conn.execute(
        "SELECT status FROM transcript_review_queue WHERE item_id = ?",
        (decided.item_id,)).fetchone()[0] == "rejected"
    # and the YouTube witnesses are untouched throughout
    assert conn.execute(
        "SELECT COUNT(*) FROM transcript_segments "
        "WHERE source = 'youtube-asr-vtt'").fetchone()[0] == 3


def test_search_prefers_whisper_over_youtube(pipeline_db, whisper_payload):
    """One video, two transcripts: the Whisper text is what search returns."""
    import app as app_module
    from scripts.pipeline import apply_verdicts

    conn = pipeline_db
    hits = app_module.search_transcripts(conn, '"crappy"')
    assert [h["video_id"] for h in hits] == ["vidTEST0001"]   # YouTube only

    apply_verdicts.apply_video(conn, "vidTEST0001", whisper_payload,
                               _verdicts_for(whisper_payload), "judge:test",
                               quiet=True, auto_apply=True)
    conn.commit()

    # the YouTube-only spelling is now invisible for this video ...
    assert app_module.search_transcripts(conn, '"crappy"') == []
    # ... and the Whisper text, including the applied correction, is searchable
    hits = app_module.search_transcripts(conn, '"Teeny Trout"')
    assert len(hits) == 1
    assert hits[0]["text"] == "Captain Teeny Trout caught seven of them."
    assert hits[0]["start_seconds"] == 16


def test_search_still_works_for_a_video_without_whisper(pipeline_db):
    import app as app_module

    conn = pipeline_db
    conn.execute("INSERT INTO videos VALUES ('vidTEST0002', 'Other', '', "
                 "'2021-02-01', '')")
    conn.execute("INSERT INTO transcript_segments "
                 "(video_id, start_seconds, duration_seconds, text, source) "
                 "VALUES ('vidTEST0002', 5.0, 2.0, 'the loons are calling', "
                 "'youtube-asr-vtt')")
    conn.commit()
    hits = app_module.search_transcripts(conn, '"loons"')
    assert [h["video_id"] for h in hits] == ["vidTEST0002"]


# --------------------------------------------------------------------------
# review queue
# --------------------------------------------------------------------------

def test_transcript_queue_registered():
    assert "transcripts" in review_service.QUEUES
    queue = review_service.get_queue("transcripts")
    assert isinstance(queue, review_service.TranscriptCandidateQueue)


def test_queue_items_and_reject(pipeline_db, whisper_payload):
    from scripts.pipeline import apply_verdicts

    conn = pipeline_db
    apply_verdicts.apply_video(conn, "vidTEST0001", whisper_payload,
                               _verdicts_for(whisper_payload), "judge:test",
                               quiet=True, auto_apply=True)
    conn.commit()
    queue = review_service.get_queue("transcripts")
    items = queue.items(conn)
    assert len(items) == 1 and queue.count(conn) == 1
    item = items[0]
    assert item.video_id == "vidTEST0001"
    assert item.kind == "transcripts"
    assert any("draft:" in sample for sample in item.samples)

    queue.reject(conn, {"item_id": item.item_id})
    row = conn.execute("SELECT * FROM transcript_review_queue "
                       "WHERE item_id = ?", (item.item_id,)).fetchone()
    assert row["status"] == "rejected"
    assert queue.count(conn) == 0
    # rejecting never touches the text
    assert conn.execute(
        "SELECT text FROM transcript_segments WHERE source = 'whisper-large-v3' "
        "ORDER BY start_seconds").fetchone()[0] == \
        "We are targeting some crappie today."


def test_queue_approve_applies_the_proposed_correction(pipeline_db,
                                                       whisper_payload):
    from scripts.pipeline import apply_verdicts

    conn = pipeline_db
    verdicts = _verdicts_for(whisper_payload)
    # the judge escalated but offered a reading -> queued *with* the proposal
    verdicts["rulings"][0]["correction"] = \
        "Captain Teeny Trout caught seven of them."
    verdicts["rulings"][0]["verdict"] = "escalate"
    apply_verdicts.apply_video(conn, "vidTEST0001", whisper_payload, verdicts,
                               "judge:test", quiet=True)
    conn.commit()

    queue = review_service.get_queue("transcripts")
    item = next(i for i in queue.items(conn)
                if i.samples and "Teeny" in " ".join(i.samples))
    result = queue.approve(conn, {"item_id": item.item_id})
    assert result["details"]["segments_edited"] == 1
    assert result["details"]["provenance"] == "human:web-review"

    assert conn.execute(
        "SELECT text FROM transcript_segments WHERE source = 'whisper-large-v3' "
        "ORDER BY start_seconds DESC").fetchone()[0] == \
        "Captain Teeny Trout caught seven of them."
    logged = conn.execute("SELECT * FROM transcript_corrections "
                          "WHERE provenance = 'human:web-review'").fetchone()
    assert logged["before_text"].startswith("Captain Tea Truck")
    row = conn.execute("SELECT * FROM transcript_review_queue "
                       "WHERE item_id = ?", (item.item_id,)).fetchone()
    assert row["status"] == "approved"
    assert "applied" in row["decision_note"]


def test_queue_approve_without_a_proposal_just_resolves(pipeline_db,
                                                        whisper_payload):
    from scripts.pipeline import apply_verdicts

    conn = pipeline_db
    apply_verdicts.apply_video(conn, "vidTEST0001", whisper_payload,
                               _verdicts_for(whisper_payload), "judge:test",
                               quiet=True, auto_apply=True)
    conn.commit()
    queue = review_service.get_queue("transcripts")
    item = queue.items(conn)[0]
    result = queue.approve(conn, {"item_id": item.item_id})
    assert result["details"]["segments_edited"] == 0
    row = conn.execute("SELECT * FROM transcript_review_queue "
                       "WHERE item_id = ?", (item.item_id,)).fetchone()
    assert row["status"] == "approved"
    assert "draft stands" in row["decision_note"]


def test_queue_is_empty_without_the_table(tmp_path):
    conn = sqlite3.connect(tmp_path / "bare.db")
    conn.row_factory = sqlite3.Row
    queue = review_service.get_queue("transcripts")
    assert queue.count(conn) == 0
    assert queue.items(conn) == []


# --------------------------------------------------------------------------
# initial_prompt construction
# --------------------------------------------------------------------------

def test_worker_liveness_is_three_valued(monkeypatch):
    """A dropped SSH connection is not evidence that the worker died.

    Reading an empty reply as "inactive" aborted a healthy 8-minute
    transcription during validation.
    """
    from scripts.pipeline import transcribe_batch as tb

    monkeypatch.setattr(tb, "wsl", lambda *a, **k: (0, "active\n", ""))
    assert tb.worker_active() is True
    monkeypatch.setattr(tb, "wsl", lambda *a, **k: (0, "inactive\n", ""))
    assert tb.worker_active() is False
    # ssh reset: non-zero rc, no output
    monkeypatch.setattr(tb, "wsl", lambda *a, **k: (255, "", "Connection reset"))
    assert tb.worker_active() is None

    def boom(*a, **k):
        raise tb.RemoteError("Connection reset by 192.168.1.156 port 22")

    monkeypatch.setattr(tb, "wsl", boom)
    assert tb.worker_active() is None


def test_await_result_survives_transient_drops(monkeypatch):
    """Only repeated *confirmed* inactive readings end the wait."""
    from scripts.pipeline import transcribe_batch as tb

    monkeypatch.setattr(tb.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def fake_wsl(script, **kwargs):
        calls["n"] += 1
        if calls["n"] < 4:
            return (0, "{}", "")           # not ready yet
        return (0, json.dumps({"n": 7, "ok": True}), "")

    monkeypatch.setattr(tb, "wsl", fake_wsl)
    # unknown every time -- must not be treated as death
    monkeypatch.setattr(tb, "worker_active", lambda: None)
    assert tb.await_result(7, poll=0, timeout=60)["ok"] is True


def test_await_result_gives_up_after_repeated_confirmed_death(monkeypatch):
    from scripts.pipeline import transcribe_batch as tb

    monkeypatch.setattr(tb.time, "sleep", lambda _s: None)
    monkeypatch.setattr(tb, "wsl", lambda *a, **k: (0, "{}", ""))
    monkeypatch.setattr(tb, "worker_active", lambda: False)
    with pytest.raises(tb.RemoteError, match="went inactive"):
        tb.await_result(7, poll=0, timeout=60)


def test_initial_prompt_extends_the_showdown_vocabulary():
    from scripts.pipeline.transcribe_batch import build_initial_prompt

    prompt = build_initial_prompt(["Funk", "Erin", "Monty", "Ken"])
    assert prompt.startswith("Matthew Posa, Monty, Rueger, Layla, "
                             "Captain Teeny Trout, Lucas, crappie")
    assert "Funk" in prompt and "Erin" in prompt
    assert prompt.count("Monty") == 1        # no duplicates
    assert prompt.endswith(".")              # punctuated prose, per ASR_SHOWDOWN

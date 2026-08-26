#!/usr/bin/env python3
"""Stage 2 — adjudicate the Whisper draft against the YouTube ASR witness.

The configuration is the one the tournament settled
(TRANSCRIPT_VERIFICATION_DESIGN, "PRODUCTION CONFIG", 2026-08-25):

* **Witnesses:** Whisper large-v3 (prompted, word timestamps) + YouTube ASR.
  Parakeet is *not* run -- adding it dropped the hard-error fix rate from 46 %
  to 26 % because its confident garbage seduces judges.
* **Judge:** ``mistral-small3.2:24b`` on MarshLair's agent ollama store, full
  packet (style card v1.1 + entity roster + disagreement flags).  Bare packets
  are banned: they made the transcript *worse* (WER +0.176).
* **Schema rule:** a ``correct`` verdict with no ``correction`` is invalid --
  one repair re-ask, then the ruling is demoted to ``escalate``.
* **Appellate tier:** a human, via the review queue.  No audio judge.

Only sentences carrying a disagreement flag or a low-confidence Whisper word
are put up for judgement; everything else is read-only context.

Runs on MysteryOfGlass (it drives ollama over the :11435 tunnel).  Reads the
Whisper JSON and the YouTube segments off Factotum, writes
``<video_id>.verdicts.json`` back beside them.

    ./venv/bin/python scripts/pipeline/judge_batch.py --limit 3
    ./venv/bin/python scripts/pipeline/judge_batch.py --only -zr_N8CDKUA
    ./venv/bin/python scripts/pipeline/judge_batch.py --status
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
TOURNAMENT_DIR = REPO_ROOT / "tools" / "tournament"
if str(TOURNAMENT_DIR) not in sys.path:
    sys.path.insert(0, str(TOURNAMENT_DIR))

from judge_prompt import ABLATIONS, build_prompt  # noqa: E402  (tools/tournament)
from runner import parse_rulings  # noqa: E402  (tools/tournament)

from scripts.pipeline import flags as flagmod  # noqa: E402
from scripts.pipeline import packets as packetmod  # noqa: E402
from scripts.pipeline.common import (  # noqa: E402
    CACHE_DIR, MARSHLAIR, PIPELINE_DIR, VERDICTS_DIR, WHISPER_DIR, Ledger,
    RemoteError, ensure_dirs, factotum, factotum_query, log,
)
from scripts.pipeline.sentences import sentences_from_segments  # noqa: E402

LEDGER_PATH = PIPELINE_DIR / "judge_ledger.jsonl"

JUDGE_MODEL = os.environ.get("POSA_JUDGE_MODEL", "mistral-small3.2:24b")
#: The agent ollama store is loopback-only on MarshLair; it needs the tunnel.
JUDGE_ENDPOINT = os.environ.get("POSA_JUDGE_ENDPOINT", "http://127.0.0.1:11435")
JUDGE_ABLATION = "full"
CELL_TIMEOUT = 1200

#: Hard ceiling on a packet's prompt.  num_ctx is 12288 tokens and the answer
#: budget is 1600, leaving ~10 700 tokens of input; at ~3.5 characters per
#: token that is ~37 k characters, so 32 k keeps a safety margin.  A packet
#: over this is split rather than truncated.
MAX_PROMPT_CHARS = 32000
SOURCE_YOUTUBE_ASR = "youtube-asr-vtt"

#: Production-only addendum to the tournament prompt.  The first live run
#: applied "wanna cut" -> "want to cut" and "Did you sleep good?" -> "Do you
#: sleep good?": the judge tidying casual speech into standard English.  That
#: is the `gutenberg-12b` smoothing failure at small scale, and it is
#: invisible to the tournament's metrics because it never touches a hard span.
CONTRACTION_GUARD = """REGISTER GUARD — this transcript is a record of how someone actually
spoke, not a tidy-up of it:

- NEVER expand a contraction or a colloquial form. "wanna" stays "wanna",
  "gonna" stays "gonna", "gimme" stays "gimme", "'em" stays "'em",
  "ain't" stays "ain't".
- NEVER correct casual or non-standard grammar. "Did you sleep good?" is
  what he said; do not make it "well". Dropped auxiliaries, doubled
  subjects, sentence fragments and false starts are all correct as they
  stand.
- NEVER swap a word for a more formal synonym, and never re-punctuate for
  elegance.
- Repetition, trailing off, and talking to a dog in baby-talk are normal
  here and are never evidence of a transcription error.

Only rule that a span is wrong when you believe a DIFFERENT WORD was spoken.
"It would read better as X" is not a correction; it is damage."""

REPAIR = """Your previous answer used the verdict "correct" for one or more spans
without supplying a "correction". A "correct" verdict with no correction states
nothing and will be discarded.

Re-emit the FULL JSON array. Every element with "verdict": "correct" must carry
a "correction" holding the full corrected sentence. If you cannot say what was
actually said, change that element's verdict to "escalate".

JSON array and nothing else."""


# --------------------------------------------------------------------------
# ollama transport (tunnel-aware)
# --------------------------------------------------------------------------

def tunnel_up(endpoint: str = JUDGE_ENDPOINT) -> bool:
    try:
        with urllib.request.urlopen(endpoint + "/api/tags", timeout=8):
            return True
    except Exception:  # noqa: BLE001
        return False


def ensure_tunnel(endpoint: str = JUDGE_ENDPOINT, attempts: int = 3) -> bool:
    """(Re)open the ssh -L tunnel to the agent ollama store.

    TOURNAMENT_RESULTS records 31 grid cells lost to this tunnel dying
    silently: *"They look like parse failures in the scorer -- check `error`
    before concluding a model failed."*  Here a drop is a retryable transport
    fault, never a model verdict.
    """
    if tunnel_up(endpoint):
        return True
    if "127.0.0.1" not in endpoint:
        return False
    port = endpoint.rsplit(":", 1)[-1]
    for _ in range(attempts):
        log(f"  · reopening ssh tunnel to :{port}")
        subprocess.Popen(
            ["setsid", "ssh", "-o", "BatchMode=yes",
             "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=15",
             "-o", "ServerAliveCountMax=1000", "-N",
             "-L", f"127.0.0.1:{port}:127.0.0.1:{port}", MARSHLAIR],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        for _ in range(10):
            time.sleep(2)
            if tunnel_up(endpoint):
                return True
    return False


def ollama_generate(prompt: str, model: str = JUDGE_MODEL,
                    endpoint: str = JUDGE_ENDPOINT, retries: int = 4) -> str:
    payload = {
        "model": model, "prompt": prompt, "stream": False, "think": False,
        "keep_alive": "20m",
        # The tournament ran at num_ctx 8192 on 40-second passages. Production
        # packets carry up to 8 flagged sentences plus context, and
        # build_prompt repeats the text three times (per-witness, then the
        # draft), so the largest measured prompt is ~6k tokens -- 12288 leaves
        # room for the 1600-token answer without truncating the packet.
        "options": {"temperature": 0, "seed": 7, "num_ctx": 12288,
                    "num_predict": 1600},
    }
    last = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                endpoint + "/api/generate",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=CELL_TIMEOUT) as response:
                return json.loads(response.read()).get("response", "")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:200]
            if "think" in body.lower() and "think" in payload:
                payload.pop("think")
                continue
            last = f"HTTP {exc.code}: {body}"
        except Exception as exc:  # noqa: BLE001 - transport faults are retryable
            last = f"{type(exc).__name__}: {exc}"
        log(f"  · judge call failed ({last}); retry {attempt + 1}/{retries}")
        ensure_tunnel(endpoint)
        time.sleep(5 * (attempt + 1))
    raise RemoteError(f"judge unreachable after {retries} attempts: {last}")


# --------------------------------------------------------------------------
# schema discipline
# --------------------------------------------------------------------------

def needs_repair(rulings):
    return [r for r in (rulings or [])
            if isinstance(r, dict)
            and str(r.get("verdict", "")).lower() == "correct"
            and not (isinstance(r.get("correction"), str) and r["correction"].strip())]


def demote(rulings) -> int:
    """Rewrite still-uncorrected 'correct' verdicts to 'escalate'."""
    count = 0
    for ruling in needs_repair(rulings):
        ruling["verdict"] = "escalate"
        ruling["_demoted"] = "correct-without-correction"
        count += 1
    return count


# --------------------------------------------------------------------------
# attaching rulings back to sentences
# --------------------------------------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", _norm(text)).strip()


def attach_ruling(ruling: dict, candidates) -> "object":
    """Find which candidate sentence a ruling is about.

    The model's ``span`` field is untrustworthy (the tournament's applier was
    scrambled by one-word spans), so matching is done three ways, cheapest
    first, and a ruling that matches nothing is dropped rather than guessed at.
    """
    span = _squash(ruling.get("span"))
    if span:
        hits = [s for s in candidates if span and span in _squash(s.text)]
        if len(hits) == 1:
            return hits[0]
        if hits:
            # ambiguous: prefer the sentence most similar to the correction
            correction = _squash(ruling.get("correction") or ruling.get("span"))
            return max(hits, key=lambda s: SequenceMatcher(
                None, _squash(s.text), correction).ratio())
    correction = _squash(ruling.get("correction"))
    if correction:
        best = max(candidates, key=lambda s: SequenceMatcher(
            None, _squash(s.text), correction).ratio(), default=None)
        if best is not None and SequenceMatcher(
                None, _squash(best.text), correction).ratio() >= 0.5:
            return best
    return None


def ruling_is_grounded(sentence, ruling, sentence_flags, sentence_lows) -> bool:
    """Is there an actual uncertainty signal behind this ruling?

    The tournament's clearest calibration failure: *"71 escalations across the
    round, only 2 of them on a genuinely hard span... they escalate on
    disfluency, which is the one thing that is reliably not an error."*  A
    ruling on a sentence that carries no flag and no low-confidence word is
    the judge free-associating, so it is dropped.
    """
    return bool(sentence_flags or sentence_lows)


# --------------------------------------------------------------------------
# data loading
# --------------------------------------------------------------------------

def load_whisper(video_id: str, cache_dir=CACHE_DIR, refresh=False) -> dict:
    path = Path(cache_dir) / f"{video_id}.whisper.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    _rc, out, _err = factotum(
        f"cat {shlex.quote(WHISPER_DIR + '/' + video_id + '.whisper.json')}",
        timeout=600)
    payload = json.loads(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def load_youtube_segments(video_id: str) -> list:
    rows = factotum_query(
        "SELECT start_seconds, duration_seconds, text FROM transcript_segments "
        "WHERE video_id = ? AND (source IS NULL OR source = ?) "
        "ORDER BY start_seconds", (video_id, SOURCE_YOUTUBE_ASR))
    return [{"start_seconds": r[0], "duration_seconds": r[1], "text": r[2]}
            for r in rows]


def load_video_meta(video_id: str) -> dict:
    rows = factotum_query(
        "SELECT title, description FROM videos WHERE video_id = ?", (video_id,))
    if not rows:
        return {"title": video_id, "description": ""}
    return {"title": rows[0][0] or video_id,
            "description": (rows[0][1] or "")[:1500]}


def load_roster() -> dict:
    people = []
    for canonical, aliases in factotum_query(
            "SELECT canonical_name, aliases FROM people"):
        try:
            parsed = json.loads(aliases or "[]")
        except (TypeError, ValueError):
            parsed = []
        people.append({"name": canonical, "aliases": parsed})
    dogs = [{"name": r[0], "breed": r[1]} for r in
            factotum_query("SELECT name, breed_primary FROM dogs")]
    return packetmod.build_roster(people, dogs)


def whisper_available_ids() -> list:
    _rc, out, _err = factotum(
        f"ls {shlex.quote(WHISPER_DIR)} 2>/dev/null || true", check=False)
    return sorted(line[:-len(".whisper.json")] for line in out.split()
                  if line.endswith(".whisper.json"))


def verdicts_available_ids() -> set:
    _rc, out, _err = factotum(
        f"ls {shlex.quote(VERDICTS_DIR)} 2>/dev/null || true", check=False)
    return {line[:-len(".verdicts.json")] for line in out.split()
            if line.endswith(".verdicts.json")}


# --------------------------------------------------------------------------
# judging one video
# --------------------------------------------------------------------------

def prepare(video_id: str, whisper: dict, youtube_segments: list,
            video_meta: dict, roster: dict):
    """Everything up to (but not including) the model call.  Pure + testable."""
    segments = whisper.get("segments") or []
    draft, spans, sentences = sentences_from_segments(segments)
    all_flags = packetmod.compute_flags(draft, spans, youtube_segments)
    lows = flagmod.low_confidence_words(segments)
    selected = flagmod.select_sentences(sentences, all_flags, lows)
    groups = flagmod.group_runs(selected)

    def make(group, packet_id):
        return packetmod.build_packet(video_meta, roster, sentences, group,
                                      all_flags, lows, youtube_segments,
                                      packet_id=packet_id)

    def fits(packet):
        return len(build_prompt(packet, extra_caution=CONTRACTION_GUARD,
                                **ABLATIONS[JUDGE_ABLATION])) <= MAX_PROMPT_CHARS

    # Grouping targets a packet size; content decides the actual prompt. A
    # packet that overruns the context would be silently truncated by ollama --
    # the flags at the end simply would not be read -- so oversized groups are
    # halved until they fit.
    built, queue, counter = [], list(groups), 0
    while queue:
        group = queue.pop(0)
        packet = make(group, f"{video_id}__{counter:04d}")
        if len(group) > 1 and not fits(packet):
            middle = len(group) // 2
            queue.insert(0, group[middle:])
            queue.insert(0, group[:middle])
            continue
        built.append(packet)
        counter += 1
    return {
        "draft": draft, "spans": spans, "sentences": sentences,
        "flags": all_flags, "lows": lows, "selected": selected,
        "packets": built,
    }


def judge_video(video_id: str, model: str = JUDGE_MODEL,
                endpoint: str = JUDGE_ENDPOINT, generate=None,
                max_packets: int = 0) -> dict:
    generate = generate or (lambda prompt: ollama_generate(prompt, model, endpoint))

    whisper = load_whisper(video_id)
    youtube_segments = load_youtube_segments(video_id)
    video_meta = load_video_meta(video_id)
    roster = load_roster()

    prepared = prepare(video_id, whisper, youtube_segments, video_meta, roster)
    sentences = prepared["sentences"]
    built = prepared["packets"]
    if max_packets:
        built = built[:max_packets]

    log(f"  · {len(sentences)} sentences, {len(prepared['flags'])} flags, "
        f"{len(prepared['lows'])} low-confidence words, "
        f"{len(prepared['selected'])} sentences under review, "
        f"{len(built)} packet(s)")

    rulings_out = []
    stats = {"packets": len(built), "parse_failures": 0, "demoted": 0,
             "repairs": 0, "dropped_unattached": 0, "dropped_ungrounded": 0,
             "confirm": 0, "correct": 0, "escalate": 0, "judge_seconds": 0.0}

    for packet in built:
        prompt = build_prompt(packet, extra_caution=CONTRACTION_GUARD,
                              **ABLATIONS[JUDGE_ABLATION])
        t0 = time.time()
        raw = generate(prompt)
        rulings, note = parse_rulings(raw)
        if rulings is None:
            stats["parse_failures"] += 1
            log(f"  ! {packet['packet_id']}: unparseable judge output")
            continue
        if needs_repair(rulings):
            stats["repairs"] += 1
            raw2 = generate(prompt + "\n\n=== YOUR PREVIOUS ANSWER ===\n" + raw
                            + "\n\n=== REPAIR INSTRUCTION ===\n" + REPAIR)
            repaired, _note2 = parse_rulings(raw2)
            if repaired is not None and len(needs_repair(repaired)) < len(needs_repair(rulings)):
                rulings = repaired
        stats["demoted"] += demote(rulings)
        stats["judge_seconds"] += time.time() - t0

        # Candidates are the whole packet window, context included: a judge
        # that wanders off and rules on an unflagged context sentence should
        # be *caught* by the grounding check below, not silently unattached.
        candidates = [sentences[i] for i in packet["_context_indices"]]
        for ruling in rulings:
            if not isinstance(ruling, dict):
                continue
            sentence = attach_ruling(ruling, candidates)
            if sentence is None:
                stats["dropped_unattached"] += 1
                continue
            sentence_flags = flagmod.flags_for_sentence(sentence, prepared["flags"])
            sentence_lows = flagmod.lows_for_sentence(sentence, prepared["lows"])
            if not ruling_is_grounded(sentence, ruling, sentence_flags, sentence_lows):
                stats["dropped_ungrounded"] += 1
                continue
            verdict = str(ruling.get("verdict", "")).lower()
            if verdict not in ("confirm", "correct", "escalate"):
                verdict = "escalate"
            stats[verdict] = stats.get(verdict, 0) + 1
            rulings_out.append({
                "packet_id": packet["packet_id"],
                "sentence_index": sentence.index,
                "start_seconds": round(sentence.start, 2),
                "end_seconds": round(sentence.end, 2),
                "draft_sentence": sentence.text,
                "span": ruling.get("span"),
                "verdict": verdict,
                "correction": ruling.get("correction"),
                "reasoning": ruling.get("reasoning"),
                "demoted": ruling.get("_demoted"),
                "witness_disagreement": "; ".join(
                    f'draft "{f["span"]}" vs '
                    + ", ".join(f'{k} heard "{v}"'
                                for k, v in f["alternatives"].items())
                    for f in sentence_flags[:4]),
                "low_confidence": [f'{l["word"]} (p={l["p"]})'
                                   for l in sentence_lows[:5]],
            })

    stats["judge_seconds"] = round(stats["judge_seconds"], 1)
    return {
        "video_id": video_id,
        "judge": model,
        "packet_ablation": JUDGE_ABLATION,
        "witness_set": "W+YT" if youtube_segments else "W",
        "judged_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "stats": stats,
        "sentence_count": len(sentences),
        "flag_count": len(prepared["flags"]),
        "lowconf_count": len(prepared["lows"]),
        "selected_count": len(prepared["selected"]),
        "rulings": rulings_out,
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only", action="append", default=[], metavar="VIDEO_ID")
    parser.add_argument("--model", default=JUDGE_MODEL)
    parser.add_argument("--endpoint", default=JUDGE_ENDPOINT)
    parser.add_argument("--max-packets", type=int, default=0,
                        help="cap packets per video (smoke tests)")
    parser.add_argument("--redo", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)

    ensure_dirs()
    ledger = Ledger(LEDGER_PATH)
    available = whisper_available_ids()

    if args.status:
        state = ledger.read()
        ok = [v for v, r in state.items() if r.get("status") == "ok"]
        failed = [v for v, r in state.items() if r.get("status") == "failed"]
        print(f"whisper transcripts : {len(available)}")
        print(f"judged              : {len(ok)}")
        print(f"failed              : {len(failed)}"
              + (f"  {failed[:8]}" if failed else ""))
        print(f"remaining           : {len(set(available) - set(ok))}")
        return 0

    done = set() if args.redo else (ledger.done_ids("ok") | verdicts_available_ids())
    todo = [v for v in (args.only or available) if v not in done]
    if args.limit:
        todo = todo[:args.limit]

    if not todo:
        log("- nothing to judge")
        return 0

    if not ensure_tunnel(args.endpoint):
        log(f"! cannot reach the judge at {args.endpoint}")
        return 1
    log(f"- judge {args.model} reachable at {args.endpoint}")

    factotum(f"mkdir -p {shlex.quote(VERDICTS_DIR)}")

    ok = failed = 0
    for index, video_id in enumerate(todo, 1):
        log(f"[{index}/{len(todo)}] {video_id}")
        t0 = time.time()
        try:
            verdicts = judge_video(video_id, args.model, args.endpoint,
                                   max_packets=args.max_packets)
            local = CACHE_DIR / f"{video_id}.verdicts.json"
            local.write_text(json.dumps(verdicts, indent=1), encoding="utf-8")
            from scripts.pipeline.common import scp_to_factotum
            scp_to_factotum(local, f"{VERDICTS_DIR}/{video_id}.verdicts.json")
            stats = verdicts["stats"]
            ledger.append({"video_id": video_id, "status": "ok",
                           "wall_s": round(time.time() - t0, 1), **stats})
            log(f"  ✓ {video_id}: {stats['correct']} correct, "
                f"{stats['escalate']} escalate, {stats['confirm']} confirm "
                f"({stats['packets']} packets, {stats['judge_seconds']}s judge)")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            log(f"  ✗ {video_id}: {exc}")
            ledger.append({"video_id": video_id, "status": "failed",
                           "error": str(exc)[:500]})

    log(f"- done: {ok} ok, {failed} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

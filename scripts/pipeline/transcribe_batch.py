#!/usr/bin/env python3
"""Stage 1 — re-transcribe the archived catalogue with faster-whisper large-v3.

Runs on MysteryOfGlass as a thin driver; the GPU work happens inside MarshLair's
WSL Ubuntu in a ``systemd-run`` unit (``scripts/pipeline/whisper_worker.py``),
which is the only shape that survives MarshLair's sshd resetting long
connections.

Per video::

    Factotum   ffmpeg  <media> -> 16 kHz mono WAV  (in /mnt/media6t/staging,
                                                    never /tmp -- 4 GB tmpfs)
    relay      Factotum -> MysteryOfGlass -> MarshLair WSL
               (scp/rsync cannot parse the space in "Blue Kitty"; the WAV goes
                over an ssh->dd pipe straight into the WSL filesystem)
    MarshLair  faster-whisper large-v3, fp16, beam 5, VAD, word timestamps,
               entity-seeded punctuated-prose initial_prompt
    Factotum   <video_id>.whisper.json in transcripts_whisper/

Both scratch WAVs reuse one filename and are overwritten by the next video, so
nothing is ever deleted and the working set never grows.

Idempotent and resumable: a video with a ledger ``ok`` record, or an existing
``.whisper.json`` on Factotum, is skipped.

    ./venv/bin/python scripts/pipeline/transcribe_batch.py --limit 3
    ./venv/bin/python scripts/pipeline/transcribe_batch.py --status
    ./venv/bin/python scripts/pipeline/transcribe_batch.py --only -zr_N8CDKUA
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pipeline import common  # noqa: E402
from scripts.pipeline.common import (  # noqa: E402
    ARCHIVE_DIR, CACHE_DIR, MARSH_UNIT, MARSH_WORKDIR, PIPELINE_DIR,
    STAGING_WAV, WHISPER_DIR, Ledger, RemoteError, ensure_dirs, factotum,
    factotum_query, log, marshlair_health, push_to_wsl,
    scp_from_factotum, scp_to_factotum, wsl,
)

LEDGER_PATH = PIPELINE_DIR / "transcribe_ledger.jsonl"
LOCAL_WAV = CACHE_DIR / "pipeline_current.wav"

#: The vocabulary line from ASR_SHOWDOWN section 1, verbatim.  It is written as
#: punctuated prose on purpose: section 4 measured that the prompt's dominant
#: effect is *formatting* (422 sentence terminators vs 19 without it), and the
#: readable output is what makes the transcripts quotable on the wiki.
BASE_VOCAB = ["Matthew Posa", "Monty", "Rueger", "Layla", "Captain Teeny Trout",
              "Lucas", "crappie", "Boundary Waters", "fillet mignon",
              "hot tent", "quinzee"]

#: faster-whisper truncates initial_prompt at 224 tokens; stay well inside it.
MAX_PROMPT_CHARS = 700

#: Transcribe in chunks of this many seconds, each re-anchored on the real
#: initial_prompt.  See "Punctuation decay" in docs/keeping-current.md: with
#: one continuous pass, Whisper stops emitting terminators ~45 minutes into a
#: 2-hour video and never recovers (one 12 120-character unpunctuated run).
#: Measured on that video, terminators per 100 words / longest unpunctuated
#: run: no chunking 6.9 / 12 120 c, 480 s 10.6 / 6 522 c, **180 s 12.9 /
#: 2 041 c**, 120 s 11.5 / 2 787 c.  180 s is also ~30 % faster than one pass
#: (rtf 23.1 vs 16.2) because short windows avoid Whisper's long-context
#: decoding and its temperature fallbacks.  0 disables chunking.
CHUNK_SECONDS = float(os.environ.get("WHISPER_CHUNK_SECONDS", "180"))

#: Where the `asr` conda env's pip-installed CUDA wheels live inside WSL.
ASR_SITE_PACKAGES = ("/home/bluekitty/miniforge3/envs/asr/lib/python3.11/"
                     "site-packages")


def build_initial_prompt(roster_names=None) -> str:
    """Base vocabulary extended with the wiki's entity roster."""
    names = list(BASE_VOCAB)
    seen = {n.lower() for n in names}
    for name in roster_names or []:
        name = (name or "").strip()
        if name and name.lower() not in seen:
            names.append(name)
            seen.add(name.lower())
    line = ", ".join(names)
    if len(line) > MAX_PROMPT_CHARS:
        line = line[:MAX_PROMPT_CHARS].rsplit(",", 1)[0]
    return line + "."


def roster_names_from_db():
    """People (canonical + aliases) and dogs from the deployed wiki DB."""
    names = []
    try:
        for (canonical, aliases) in factotum_query(
                "SELECT canonical_name, aliases FROM people"):
            if canonical:
                names.append(canonical)
            try:
                for alias in json.loads(aliases or "[]"):
                    names.append(alias)
            except (TypeError, ValueError):
                pass
        for (name,) in factotum_query("SELECT name FROM dogs"):
            if name:
                names.append(name)
    except Exception as exc:  # noqa: BLE001 - the base vocabulary is enough
        log(f"! roster lookup failed ({exc}); using base vocabulary only")
    # Rows like "Matthew's Brother" are placeholders for an unnamed person and
    # their aliases are ordinary English words ("mom", "dad", "brother") --
    # feeding those to Whisper burns prompt budget and teaches it nothing.
    generic = {"mom", "dad", "brother", "sister", "wife", "husband"}
    return [n for n in names
            if n and not n.lower().startswith("matthew's")
            and n.lower() not in generic]


# --------------------------------------------------------------------------
# MarshLair worker lifecycle
# --------------------------------------------------------------------------

def worker_active():
    """``True`` / ``False`` / ``None`` when the box could not be asked.

    The three-valued answer matters.  MarshLair's sshd resets connections at
    random (CLAUDE.md), and a reset makes this call return no output -- which
    an ``out.startswith("active")`` test reads as "the worker is dead".  That
    aborted a perfectly healthy 8-minute transcription once already, and it is
    the same trap TOURNAMENT_RESULTS records under *"they look like parse
    failures in the scorer -- check `error` before concluding a model failed"*.
    A transport fault is never evidence about the worker.
    """
    try:
        rc, out, _err = wsl(f"systemctl is-active {MARSH_UNIT} || true",
                            check=False, timeout=90)
    except Exception:  # noqa: BLE001 - ssh reset / timeout: we simply don't know
        return None
    if rc != 0 and not out.strip():
        return None
    text = out.strip()
    if not text:
        return None
    return text.startswith("active")


def stop_worker() -> None:
    wsl(f"sudo systemctl stop {MARSH_UNIT} 2>/dev/null || true\n"
        f"sudo systemctl reset-failed {MARSH_UNIT} 2>/dev/null || true\n"
        f"echo STOPPED\n", check=False, timeout=180)


def deploy_worker() -> None:
    """Copy the worker into WSL and (re)start it as a transient unit."""
    source = (REPO_ROOT / "scripts" / "pipeline" / "whisper_worker.py").read_bytes()
    import base64
    encoded = base64.b64encode(source).decode()
    # The script content is base64'd so no quoting survives to a shell, and the
    # whole thing arrives on stdin (heredoc pattern) so cmd.exe never sees an
    # operator.  CLAUDE.md, "the base64 upgrade".
    script = f"""
set -e
mkdir -p {MARSH_WORKDIR}
printf %s '{encoded}' | base64 -d > {MARSH_WORKDIR}/worker.py
printf 0 > {MARSH_WORKDIR}/stop
if ! systemctl is-active --quiet {MARSH_UNIT}; then
  : > {MARSH_WORKDIR}/ready
fi
# CTranslate2 dlopen()s libcublas/libcudnn out of the env's pip-installed
# nvidia wheels.  `conda activate` would set this up; systemd-run does not
# source a profile, so the search path is assembled explicitly -- without it
# the model loads and every transcribe() dies with "libcublas.so.12 is not
# found or cannot be loaded".
NVLIBS=$(ls -d {ASR_SITE_PACKAGES}/nvidia/*/lib 2>/dev/null | paste -sd:)
if systemctl is-active --quiet {MARSH_UNIT}; then
  echo ALREADY_ACTIVE
else
  sudo systemctl reset-failed {MARSH_UNIT} 2>/dev/null || true
  sudo systemd-run --unit={MARSH_UNIT} --uid=1000 --gid=1000 \\
    --property=WorkingDirectory={MARSH_WORKDIR} \\
    --setenv=HOME=/home/bluekitty \\
    --setenv=POSA_ASR_WORKDIR={MARSH_WORKDIR} \\
    --setenv=LD_LIBRARY_PATH="$NVLIBS" \\
    /home/bluekitty/miniforge3/envs/asr/bin/python {MARSH_WORKDIR}/worker.py
  echo STARTED
fi
"""
    _rc, out, _err = wsl(script, timeout=300)
    log(f"- worker: {out.strip().splitlines()[-1] if out.strip() else 'ok'}")


def wait_for_model(timeout: float = 900.0) -> None:
    """Block until the *current* worker has the model on the GPU.

    Watches the ``ready`` file, not the journal: a previous unit's
    ``MODEL_LOADED`` line is still in the journal and matches instantly.
    ``deploy_worker`` truncates the file before starting, so a non-empty
    ``ready`` means this invocation.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        _rc, out, _err = wsl(f"cat {MARSH_WORKDIR}/ready 2>/dev/null || true",
                             check=False, timeout=120)
        if out.strip():
            log(f"- worker ready (pid {out.split()[0]})")
            return
        if worker_active() is False:   # never `not ...` -- None means "unknown"
            _rc, journal, _err = wsl(
                f"sudo journalctl -u {MARSH_UNIT} -n 60 --no-pager",
                check=False, timeout=120)
            raise RemoteError("whisper worker died before loading the model; "
                              f"journal tail:\n{journal[-800:]}")
        time.sleep(10)
    raise RemoteError("timed out waiting for the worker to become ready")


def next_job_number() -> int:
    _rc, out, _err = wsl(
        f"cat {MARSH_WORKDIR}/job.json 2>/dev/null || echo '{{}}'", check=False)
    try:
        return int(json.loads(out.strip() or "{}").get("n", 0)) + 1
    except (ValueError, TypeError):
        return 1


def submit_job(n: int, video_id: str, prompt: str,
               chunk_seconds: float = CHUNK_SECONDS) -> None:
    import base64
    payload = base64.b64encode(
        json.dumps({"n": n, "video_id": video_id, "prompt": prompt,
                    "condition_on_previous_text": True,
                    "chunk_seconds": chunk_seconds}).encode()
    ).decode()
    wsl(f"printf %s '{payload}' | base64 -d > {MARSH_WORKDIR}/job.json.tmp\n"
        f"mv {MARSH_WORKDIR}/job.json.tmp {MARSH_WORKDIR}/job.json\n"
        f"echo SUBMITTED\n", timeout=120)


#: Consecutive *confirmed* inactive readings before we call the worker dead.
DEAD_WORKER_STRIKES = 3


def await_result(n: int, poll: float = 15.0, timeout: float = 5400.0) -> dict:
    """Poll for the worker's result with short reconnecting calls.

    A crash looks exactly like "still running" unless the unit is checked --
    but a dropped SSH connection looks exactly like a crash unless the check
    can say "I don't know".  So a single inactive reading is never enough:
    the result file is re-read first (the worker may have finished and exited
    between the two calls) and the unit has to come back inactive
    :data:`DEAD_WORKER_STRIKES` times in a row.
    """
    deadline = time.time() + timeout
    strikes = 0
    while time.time() < deadline:
        time.sleep(poll)
        try:
            _rc, out, _err = wsl(
                f"cat {MARSH_WORKDIR}/result.json 2>/dev/null || echo '{{}}'",
                check=False, timeout=300)
        except Exception as exc:  # noqa: BLE001 - transport fault, just retry
            log(f"  · poll failed ({type(exc).__name__}); retrying")
            continue
        try:
            payload = json.loads(out.strip() or "{}")
        except ValueError:
            continue
        if payload.get("n") == n:
            return payload

        alive = worker_active()
        if alive is False:
            strikes += 1
            if strikes >= DEAD_WORKER_STRIKES:
                raise RemoteError("whisper worker went inactive without "
                                  f"producing result n={n}")
            log(f"  · unit reported inactive ({strikes}/{DEAD_WORKER_STRIKES})")
        else:
            strikes = 0
    raise RemoteError(f"timed out waiting for result n={n}")


# --------------------------------------------------------------------------
# per-video work
# --------------------------------------------------------------------------

def extract_audio(media_path: str) -> None:
    factotum(
        "ffmpeg -nostdin -y -loglevel error -i "
        f"{shlex.quote(media_path)} -vn -ac 1 -ar 16000 -c:a pcm_s16le "
        f"{shlex.quote(STAGING_WAV)}",
        timeout=1800)


def existing_whisper_ids() -> set:
    _rc, out, _err = factotum(
        f"ls {shlex.quote(WHISPER_DIR)} 2>/dev/null || true", check=False)
    return {line[:-len(".whisper.json")] for line in out.split()
            if line.endswith(".whisper.json")}


def transcribe_one(video_id: str, media_path: str, prompt: str,
                   ledger: Ledger) -> dict:
    t0 = time.time()
    log(f"  · extracting audio on Factotum")
    extract_audio(media_path)

    log("  · Factotum -> MysteryOfGlass")
    scp_from_factotum(STAGING_WAV, LOCAL_WAV)
    size_mb = LOCAL_WAV.stat().st_size / 1e6

    log(f"  · MysteryOfGlass -> MarshLair WSL ({size_mb:.0f} MB)")
    push_to_wsl(LOCAL_WAV, f"{MARSH_WORKDIR}/current.wav")

    n = next_job_number()
    submit_job(n, video_id, prompt)
    log(f"  · job n={n} submitted; polling")
    result = await_result(n)

    if not result.get("ok"):
        raise RemoteError(result.get("error") or "worker reported failure")

    out_path = CACHE_DIR / f"{video_id}.whisper.json"
    payload = {"video_id": video_id, "segments": result["segments"],
               "meta": result.get("meta", {})}
    out_path.write_text(json.dumps(payload), encoding="utf-8")

    factotum(f"mkdir -p {shlex.quote(WHISPER_DIR)}")
    scp_to_factotum(out_path, f"{WHISPER_DIR}/{video_id}.whisper.json")

    meta = result.get("meta", {})
    record = {
        "video_id": video_id, "status": "ok",
        "segments": meta.get("n_segments"),
        "audio_duration_s": meta.get("audio_duration_s"),
        "transcribe_wall_s": meta.get("transcribe_wall_s"),
        "realtime_factor": meta.get("realtime_factor"),
        "driver_wall_s": round(time.time() - t0, 1),
        "media": media_path,
    }
    ledger.append(record)
    log(f"  ✓ {video_id}: {meta.get('n_segments')} segments, "
        f"{meta.get('transcribe_wall_s')}s gpu, "
        f"{record['driver_wall_s']}s wall, rtf {meta.get('realtime_factor')}")
    return record


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def status(ledger: Ledger, media: dict) -> None:
    state = ledger.read()
    ok = [v for v, r in state.items() if r.get("status") == "ok"]
    failed = [v for v, r in state.items() if r.get("status") == "failed"]
    print(f"archive media : {len(media)}")
    print(f"transcribed   : {len(ok)}")
    print(f"failed        : {len(failed)}"
          + (f"  {failed[:8]}" if failed else ""))
    print(f"remaining     : {len(set(media) - set(ok))}")
    gpu = [r.get("transcribe_wall_s") or 0 for r in state.values()
           if r.get("status") == "ok"]
    if gpu:
        print(f"gpu seconds   : {sum(gpu):.0f} "
              f"(mean {sum(gpu)/len(gpu):.0f}s/video)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--limit", type=int, default=0,
                        help="stop after N videos (0 = all remaining)")
    parser.add_argument("--only", action="append", default=[],
                        metavar="VIDEO_ID", help="transcribe just these ids")
    parser.add_argument("--archive-dir", default=ARCHIVE_DIR)
    parser.add_argument("--status", action="store_true",
                        help="print progress and exit")
    parser.add_argument("--redo", action="store_true",
                        help="ignore the ledger for --only ids")
    parser.add_argument("--restart-worker", action="store_true",
                        help="stop any running MarshLair worker first "
                             "(needed after editing whisper_worker.py)")
    args = parser.parse_args(argv)

    ensure_dirs()
    ledger = Ledger(LEDGER_PATH)

    log(f"- scanning {args.archive_dir} on Factotum")
    media = common.archive_media(args.archive_dir)
    log(f"- {len(media)} archived media files")

    if args.status:
        status(ledger, media)
        return 0

    done = ledger.done_ids("ok")
    if not args.redo:
        done |= existing_whisper_ids()

    if args.only:
        todo = [v for v in args.only if v in media]
        missing = [v for v in args.only if v not in media]
        for video_id in missing:
            log(f"! {video_id}: no media in the archive")
        if not args.redo:
            todo = [v for v in todo if v not in done]
    else:
        todo = [v for v in media if v not in done]
    if args.limit:
        todo = todo[:args.limit]

    if not todo:
        log("- nothing to do")
        status(ledger, media)
        return 0

    used = marshlair_health()
    log(f"- MarshLair reachable, {used} MiB VRAM in use "
        f"({'chat stack resident, normal' if used < 3000 else 'CHECK: heavy resident'})")

    prompt = build_initial_prompt(roster_names_from_db())
    log(f"- initial_prompt: {prompt}")

    if args.restart_worker:
        stop_worker()
    deploy_worker()
    wait_for_model()

    log(f"- {len(todo)} video(s) to transcribe")
    ok = failed = 0
    for index, video_id in enumerate(todo, 1):
        log(f"[{index}/{len(todo)}] {video_id}")
        try:
            transcribe_one(video_id, media[video_id], prompt, ledger)
            ok += 1
        except Exception as exc:  # noqa: BLE001 - one bad video must not stop the batch
            failed += 1
            log(f"  ✗ {video_id}: {exc}")
            ledger.append({"video_id": video_id, "status": "failed",
                           "error": str(exc)[:500]})
            try:
                if worker_active() is False:
                    log("  · worker is down; restarting")
                    deploy_worker()
                    wait_for_model()
            except Exception as restart_exc:  # noqa: BLE001
                log(f"  ✗ cannot restart worker: {restart_exc}")
                break

    log(f"- done: {ok} ok, {failed} failed")
    status(ledger, media)
    return 0


if __name__ == "__main__":
    sys.exit(main())

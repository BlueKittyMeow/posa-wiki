#!/usr/bin/env python3
"""faster-whisper worker — runs inside MarshLair's WSL Ubuntu, not here.

``scripts/pipeline/transcribe_batch.py`` copies this file into
``~/posa_asr/worker.py`` on MarshLair and starts it as a ``systemd-run``
transient unit.  It is in the repo (rather than only on the box) so the thing
that actually produces the transcripts is version-controlled and reviewable.

Why a resident worker rather than one process per video: ``large-v3`` takes
~13 s to load warm, and the batch is 100+ videos.  Holding the model on the GPU
turns 25 minutes of reloading into one load.  The WSL VM has 8 GB of RAM, so
the model must stay GPU-resident -- never CPU-offload on this box (CLAUDE.md).

Protocol (one job at a time, one reusable WAV filename, nothing ever deleted):

    driver  writes  ~/posa_asr/current.wav        (overwritten per video)
    driver  writes  ~/posa_asr/job.json           {"n": 7, "video_id": ..., "prompt": ...}
    worker  writes  ~/posa_asr/result.json        {"n": 7, "ok": true, "segments": [...]}
    driver  polls result.json until its "n" matches

Decode settings are the ones ASR_SHOWDOWN section 5 recommends and the
tournament's witness transcripts were produced with: float16, beam 5, VAD on,
word timestamps on, punctuated-prose ``initial_prompt``.
"""

import json
import os
import sys
import time
import traceback

WORKDIR = os.environ.get("POSA_ASR_WORKDIR", "/home/bluekitty/posa_asr")
JOB = os.path.join(WORKDIR, "job.json")
RESULT = os.path.join(WORKDIR, "result.json")
WAV = os.path.join(WORKDIR, "current.wav")
STOP = os.path.join(WORKDIR, "stop")
READY = os.path.join(WORKDIR, "ready")
IDLE_TIMEOUT = float(os.environ.get("POSA_ASR_IDLE_TIMEOUT", "7200"))
POLL_SECONDS = 2.0


def write_atomic(path, payload):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


SAMPLE_RATE = 16000


class _Info:
    """Duck-type of faster-whisper's TranscriptionInfo, for the chunked path."""

    def __init__(self, duration):
        self.duration = duration


def _collect(segments_iter, offset=0.0):
    out = []
    for seg in segments_iter:
        out.append({
            "start": round(seg.start + offset, 3),
            "end": round(seg.end + offset, 3),
            "text": seg.text,
            "words": [
                {"w": w.word, "s": round(w.start + offset, 3),
                 "e": round(w.end + offset, 3), "p": round(w.probability, 3)}
                for w in (seg.words or [])
            ],
        })
    return out


def transcribe(model, prompt, condition, chunk_seconds):
    """Whole-file or chunk-anchored transcription.

    With ``chunk_seconds`` set, the audio is decoded once and cut into
    fixed-length pieces; every piece is transcribed with the *same* real
    ``initial_prompt`` and conditioning enabled within the piece, then the
    timestamps are shifted back. That keeps the prompt's formatting effect
    alive for the whole video without letting drift accumulate.
    """
    kwargs = dict(language="en", word_timestamps=True, vad_filter=True,
                  initial_prompt=prompt, beam_size=5,
                  condition_on_previous_text=condition)
    if not chunk_seconds:
        segments_iter, info = model.transcribe(WAV, **kwargs)
        return _collect(segments_iter), info

    from faster_whisper.audio import decode_audio

    audio = decode_audio(WAV, sampling_rate=SAMPLE_RATE)
    total = len(audio) / SAMPLE_RATE
    step = int(chunk_seconds * SAMPLE_RATE)
    segments = []
    for index, begin in enumerate(range(0, len(audio), step)):
        piece = audio[begin:begin + step]
        if len(piece) < SAMPLE_RATE:      # under a second of tail; nothing to say
            continue
        offset = begin / SAMPLE_RATE
        piece_iter, _piece_info = model.transcribe(piece, **kwargs)
        got = _collect(piece_iter, offset=offset)
        segments.extend(got)
        print(f"  CHUNK {index} @{offset:.0f}s -> {len(got)} segs", flush=True)
    return segments, _Info(total)


def main():
    from faster_whisper import WhisperModel

    os.makedirs(WORKDIR, exist_ok=True)
    t0 = time.time()
    model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    print(f"MODEL_LOADED {time.time() - t0:.1f}s", flush=True)
    # The driver watches this file rather than the journal: a previous unit's
    # "MODEL_LOADED" line is still in the journal and would be matched
    # instantly, letting the driver submit a job to a worker that is not up.
    with open(READY, "w", encoding="utf-8") as handle:
        handle.write(f"{os.getpid()} {time.time():.0f}\n")

    last_n = -1
    done = read_json(RESULT)
    if done and isinstance(done.get("n"), int):
        last_n = done["n"]
    idle_since = time.time()

    while True:
        # Nothing in this pipeline deletes a file, so "stop" is a flag whose
        # *content* is the signal: write 1 to ask the worker to exit.
        try:
            with open(STOP, "r", encoding="utf-8") as handle:
                if handle.read().strip() == "1":
                    print("STOP_FILE_SEEN", flush=True)
                    break
        except OSError:
            pass
        if time.time() - idle_since > IDLE_TIMEOUT:
            print("IDLE_TIMEOUT", flush=True)
            break

        job = read_json(JOB)
        if not job or not isinstance(job.get("n"), int) or job["n"] <= last_n:
            time.sleep(POLL_SECONDS)
            continue

        idle_since = time.time()
        n = job["n"]
        video_id = job.get("video_id") or "?"
        prompt = job.get("prompt") or None
        # Punctuation decay, measured 2026-08-25 (see docs/keeping-current.md):
        # the initial_prompt only conditions the FIRST window, and its
        # formatting effect reaches the rest of the video *through*
        # conditioning -- so turning conditioning off does not cure the decay,
        # it throws the punctuation away everywhere (3.4 terminators per 100
        # words against 16.6). But leaving it on lets the model drift into
        # unpunctuated lowercase and never recover.
        #
        # The fix is to re-anchor: transcribe in chunks, each one starting
        # fresh from the real initial_prompt with conditioning ON *inside* the
        # chunk. Drift cannot accumulate past a chunk boundary.
        condition = bool(job.get("condition_on_previous_text", True))
        chunk_seconds = float(job.get("chunk_seconds") or 0)
        print(f"JOB_START n={n} video={video_id} condition={condition} "
              f"chunk={chunk_seconds or 'off'}", flush=True)
        start = time.time()
        try:
            segments, info = transcribe(model, prompt, condition, chunk_seconds)
            elapsed = time.time() - start
            payload = {
                "n": n, "ok": True, "video_id": video_id,
                "segments": segments,
                "meta": {
                    "engine": "faster-whisper large-v3 float16",
                    "beam_size": 5, "vad_filter": True,
                    "word_timestamps": True,
                    "condition_on_previous_text": condition,
                    "chunk_seconds": chunk_seconds or None,
                    "initial_prompt": prompt,
                    "audio_duration_s": round(info.duration, 2),
                    "transcribe_wall_s": round(elapsed, 2),
                    "realtime_factor": round(info.duration / elapsed, 2)
                                       if elapsed else None,
                    "n_segments": len(segments),
                    "transcribed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                },
            }
            print(f"JOB_OK n={n} video={video_id} segs={len(segments)} "
                  f"{elapsed:.1f}s rtf={payload['meta']['realtime_factor']}", flush=True)
        except Exception as exc:  # noqa: BLE001 - one bad file must not kill the batch
            traceback.print_exc()
            payload = {"n": n, "ok": False, "video_id": video_id,
                       "error": f"{type(exc).__name__}: {exc}"[:500]}
            print(f"JOB_FAIL n={n} video={video_id}: {exc}", flush=True)

        write_atomic(RESULT, payload)
        last_n = n

    print("WORKER_EXIT", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

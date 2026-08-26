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
        print(f"JOB_START n={n} video={video_id}", flush=True)
        start = time.time()
        try:
            segments_iter, info = model.transcribe(
                WAV, language="en", word_timestamps=True, vad_filter=True,
                initial_prompt=prompt, beam_size=5,
            )
            segments = []
            for seg in segments_iter:
                segments.append({
                    "start": round(seg.start, 3),
                    "end": round(seg.end, 3),
                    "text": seg.text,
                    "words": [
                        {"w": w.word, "s": round(w.start, 3),
                         "e": round(w.end, 3), "p": round(w.probability, 3)}
                        for w in (seg.words or [])
                    ],
                })
            elapsed = time.time() - start
            payload = {
                "n": n, "ok": True, "video_id": video_id,
                "segments": segments,
                "meta": {
                    "engine": "faster-whisper large-v3 float16",
                    "beam_size": 5, "vad_filter": True,
                    "word_timestamps": True,
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

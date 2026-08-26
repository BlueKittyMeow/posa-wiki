"""Production transcript pipeline.

Three stages, all idempotent, ledger-driven and resumable:

``transcribe_batch.py``
    Factotum archive media -> 16 kHz mono WAV -> faster-whisper large-v3 on
    MarshLair -> ``<video_id>.whisper.json`` back on Factotum.

``judge_batch.py``
    Whisper draft + YouTube ASR witness -> word-level disagreement flags ->
    only the flagged sentences -> ``mistral-small3.2:24b`` -> sentence-level
    rulings in ``<video_id>.verdicts.json``.

``apply_verdicts.py``
    Verdicts -> the wiki database: Whisper segments, applied corrections
    (logged), escalations queued for a human.

The configuration is the one settled by the adjudicator tournament; see
``docs/research/TRANSCRIPT_VERIFICATION_DESIGN.md`` (PRODUCTION CONFIG) and
``docs/research/TOURNAMENT_RESULTS.md``.
"""

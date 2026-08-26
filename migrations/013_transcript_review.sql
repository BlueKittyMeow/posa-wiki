-- Migration 013: whisper transcripts, judge provenance, and the transcript
-- review queue.
--
-- Background: docs/research/TRANSCRIPT_VERIFICATION_DESIGN.md ("PRODUCTION
-- CONFIG", settled 2026-08-25) and docs/research/TOURNAMENT_RESULTS.md.
--
-- The production pipeline is:
--
--   scripts/pipeline/transcribe_batch.py   archive media -> faster-whisper
--                                          large-v3 -> <id>.whisper.json
--   scripts/pipeline/judge_batch.py        whisper + YouTube ASR witnesses ->
--                                          mistral-small3.2:24b -> verdicts
--   scripts/pipeline/apply_verdicts.py     verdicts -> this database
--
-- Three things this migration has to make possible:
--
-- 1. TWO transcript sources can coexist for one video. transcript_segments
--    gains a `source` column so Whisper rows sit alongside the YouTube ASR
--    rows that scripts/ingest_transcripts.py already wrote. Nothing is ever
--    deleted; /search simply *prefers* the Whisper rows for a video that has
--    them (see search_transcripts() in app.py).
--
-- 2. Per-video pipeline state has to be queryable. transcript_status is one
--    row per video, so the Whisper/judge state lands in extra columns rather
--    than extra rows -- `source`/`status`/`segment_count` keep meaning "the
--    YouTube ASR ingest", exactly as migration 010 defined them.
--
-- 3. Every applied correction and every escalation has to stay auditable.
--    transcript_corrections is the applied-change log; transcript_review_queue
--    is the human queue behind /admin/review/transcripts.
--
-- ALL LLM output is candidate-only. A 'correct' verdict edits the Whisper
-- draft and leaves a row in transcript_corrections saying which model said so;
-- an 'escalate' verdict never touches the text at all.

-- --------------------------------------------------------------------------
-- 1. Segment provenance
-- --------------------------------------------------------------------------

-- 'youtube-asr-vtt' (migration 010 / ingest_transcripts.py) or
-- 'whisper-large-v3' (transcribe_batch.py -> apply_verdicts.py).
-- Existing rows predate the column and are all YouTube ASR.
ALTER TABLE transcript_segments ADD COLUMN source VARCHAR;
UPDATE transcript_segments SET source = 'youtube-asr-vtt' WHERE source IS NULL;

CREATE INDEX IF NOT EXISTS idx_transcript_segments_video_source
    ON transcript_segments (video_id, source);

-- --------------------------------------------------------------------------
-- 2. Per-video pipeline state
-- --------------------------------------------------------------------------

--   whisper_status  NULL      -- not transcribed
--                   'ingested'
--                   'error'
--   judge_status    NULL      -- not judged
--                   'judged'
--                   'failed'
ALTER TABLE transcript_status ADD COLUMN whisper_status VARCHAR;
ALTER TABLE transcript_status ADD COLUMN whisper_segment_count INTEGER;
ALTER TABLE transcript_status ADD COLUMN whisper_ingested_at TIMESTAMP;
ALTER TABLE transcript_status ADD COLUMN judge_status VARCHAR;
ALTER TABLE transcript_status ADD COLUMN judged_at TIMESTAMP;
ALTER TABLE transcript_status ADD COLUMN corrections_applied INTEGER;
ALTER TABLE transcript_status ADD COLUMN escalations_queued INTEGER;

-- --------------------------------------------------------------------------
-- 3. Applied-correction log
-- --------------------------------------------------------------------------

-- One row per segment edit actually written. Keeps the pre-edit text so a
-- correction is reversible by hand, and records who said so.
CREATE TABLE IF NOT EXISTS transcript_corrections (
    correction_id  INTEGER PRIMARY KEY,
    video_id       VARCHAR NOT NULL REFERENCES videos(video_id),
    segment_id     INTEGER REFERENCES transcript_segments(segment_id),
    start_seconds  REAL,
    before_text    TEXT NOT NULL,
    after_text     TEXT NOT NULL,
    span           TEXT,
    reasoning      TEXT,
    -- 'judge:mistral-small3.2:24b' or 'human:web-review'
    provenance     VARCHAR NOT NULL,
    applied_at     TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_transcript_corrections_video
    ON transcript_corrections (video_id);

-- --------------------------------------------------------------------------
-- 4. Human review queue
-- --------------------------------------------------------------------------

-- item_id is a stable content hash so a re-run of judge_batch/apply_verdicts
-- never duplicates a row Lara has already decided (INSERT OR IGNORE).
--   status  'open'      -- waiting for a human
--           'approved'  -- proposed_correction applied, or simply resolved
--           'rejected'  -- the Whisper draft stands
CREATE TABLE IF NOT EXISTS transcript_review_queue (
    item_id              VARCHAR PRIMARY KEY,
    video_id             VARCHAR NOT NULL REFERENCES videos(video_id),
    start_seconds        REAL,
    end_seconds          REAL,
    draft_sentence       TEXT,
    witness_disagreement TEXT,
    judge_reasoning      TEXT,
    proposed_correction  TEXT,
    status               VARCHAR NOT NULL DEFAULT 'open',
    created_at           TIMESTAMP,
    decided_at           TIMESTAMP,
    decision_note        TEXT
);

CREATE INDEX IF NOT EXISTS idx_transcript_review_queue_status
    ON transcript_review_queue (status, video_id);

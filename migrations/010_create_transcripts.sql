-- Migration 010: transcript storage + full-text search
--
-- Transcripts come from the local subtitle sidecar files produced by the
-- yt-dlp channel archive (scripts/archive_channel.sh). On the server those
-- live under /mnt/media6t/archive/posa/<dirname>/<name> [<video_id>].en.vtt.
-- scripts/ingest_transcripts.py parses them into transcript_segments and
-- records per-video state in transcript_status.
--
-- transcripts_fts mirrors the videos_fts pattern from build_fts_index.py:
-- an external-content FTS5 table kept in sync by three triggers.

CREATE TABLE IF NOT EXISTS transcript_segments (
    segment_id      INTEGER PRIMARY KEY,
    video_id        VARCHAR NOT NULL REFERENCES videos(video_id),
    start_seconds   REAL NOT NULL,
    duration_seconds REAL,
    text            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transcript_segments_video_start
    ON transcript_segments (video_id, start_seconds);

-- One row per video we have attempted. status is one of:
--   'ingested'    -- segments are in transcript_segments
--   'no_captions' -- archive has no usable subtitle sidecar for this video
--   'error'       -- parse/insert failed; see error
-- source identifies where the text came from, e.g. 'youtube-asr-vtt'
-- (future: 'whisper-large-v3').
CREATE TABLE IF NOT EXISTS transcript_status (
    video_id      VARCHAR PRIMARY KEY REFERENCES videos(video_id),
    status        VARCHAR NOT NULL,
    source        VARCHAR,
    language      VARCHAR,
    segment_count INTEGER,
    ingested_at   TIMESTAMP,
    error         TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts USING fts5(
    text,
    content='transcript_segments',
    content_rowid='segment_id'
);

CREATE TRIGGER IF NOT EXISTS transcript_segments_ai
AFTER INSERT ON transcript_segments BEGIN
    INSERT INTO transcripts_fts(rowid, text) VALUES (new.segment_id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS transcript_segments_ad
AFTER DELETE ON transcript_segments BEGIN
    INSERT INTO transcripts_fts(transcripts_fts, rowid, text)
    VALUES ('delete', old.segment_id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS transcript_segments_au
AFTER UPDATE ON transcript_segments BEGIN
    INSERT INTO transcripts_fts(transcripts_fts, rowid, text)
    VALUES ('delete', old.segment_id, old.text);
    INSERT INTO transcripts_fts(rowid, text) VALUES (new.segment_id, new.text);
END;

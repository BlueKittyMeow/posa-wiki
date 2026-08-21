-- Migration 008: add numeric duration column
--
-- videos.duration holds a pre-formatted human string ('0:21', '9:31', '10:00:36'),
-- which sorts lexicographically and therefore gives nonsense ordering for
-- ?sort=duration. Store the parsed value in seconds so ORDER BY is numeric.
--
-- Backfill with: python scripts/backfill_duration_seconds.py

ALTER TABLE videos ADD COLUMN duration_seconds INTEGER;

CREATE INDEX IF NOT EXISTS idx_videos_duration_seconds
    ON videos (duration_seconds);

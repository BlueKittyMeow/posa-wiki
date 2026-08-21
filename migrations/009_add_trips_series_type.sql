-- Migration 009: add trips.series_type
--
-- Schema drift fix. app.py's /series and /trips routes (added in the
-- "separate series from trips" work) query trips.series_type, but that
-- column was never added via create_database.py or a tracked migration —
-- it only exists in the live posa_wiki.db because the untracked one-off
-- script separate_series_trips.py (now archived under scripts/archive/)
-- was run manually against it directly. This migration codifies that
-- change so a fresh database build (create_database.py + migrations) ends
-- up with the same schema the live DB already has.
--
-- Do NOT run this against posa_wiki.db — the column already exists there
-- (added by separate_series_trips.py) and this ALTER would error/no-op
-- depending on run_migration.py's handling of duplicate columns.

ALTER TABLE trips ADD COLUMN series_type VARCHAR DEFAULT 'trip';

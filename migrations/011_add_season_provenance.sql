-- Migration 011: season provenance on videos
--
-- Seasons are a VIDEO FACET, not a series (owner decision 2026-08-21).
-- videos.season already exists (created by create_database.py, almost
-- entirely NULL); these two columns record *how much* we trust the value
-- and *where it came from*, so a later re-derivation never stomps a human.
--
--   season             'winter' | 'spring' | 'summer' | 'fall'
--                      NULL means UNKNOWN, which is a legitimate value --
--                      never guess a season just to fill the column.
--   season_confidence  'high'   -- an unambiguous rule matched
--                      'medium' -- proposed only, routed to review
--                      'human'  -- a person decided; UNTOUCHABLE by scripts
--   season_source      the rule name ('title:winter', 'tag:winter camping',
--                      ...) or 'human:web-review'
--
-- Upload date is deliberately NOT evidence: uploads lag filming, badly so
-- for the early videos.

ALTER TABLE videos ADD COLUMN season_confidence VARCHAR;
ALTER TABLE videos ADD COLUMN season_source VARCHAR;

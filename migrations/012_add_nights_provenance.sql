-- Migration 012: trip-length (nights) provenance on videos
--
-- Trip length is a VIDEO FACET, exactly like season (migration 011) --
-- "how many nights was he out?" is a property of the trip the video covers,
-- not a series. videos.number_of_nights already exists (created by
-- create_database.py, 100% NULL); these two columns record *how much* we
-- trust the value and *where it came from*, so a later re-derivation never
-- stomps a human decision.
--
--   number_of_nights   INTEGER >= 0.
--                      NULL means UNKNOWN, which is a legitimate value --
--                      never guess a trip length just to fill the column.
--                      In particular 0 is never *inferred* from the absence
--                      of overnight evidence: a Hike and Cook is probably a
--                      day trip, but "probably" is a review-tier answer.
--   nights_confidence  'high'   -- the title states it (nights exact, or a
--                                  days count converted N-1, or "overnight")
--                      'medium' -- proposed only, routed to review
--                      'human'  -- a person decided; UNTOUCHABLE by scripts
--   nights_source      the rule name ('title:nights', 'title:days-minus-one',
--                      'title:days+night-of', 'title:overnight', ...) or
--                      'human:web-review'
--
-- Days -> nights conversion is owner-approved and validated against his own
-- titles: "8 Day Wilderness Adventure with My Dog (Night 7 of 7)" pairs an
-- 8-day framing with a 7-night one. When a title carries both forms they are
-- cross-checked; an inconsistent pair is never auto-written.

ALTER TABLE videos ADD COLUMN nights_confidence VARCHAR;
ALTER TABLE videos ADD COLUMN nights_source VARCHAR;

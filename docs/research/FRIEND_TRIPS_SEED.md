# Friend Trips — future collection seed list

*Goal (Lara, 2026-08-20): a collection of videos where Matthew camps with a
GROUP of friends — more than just Lucas/Teeny Trout, and excluding
parents/brother family trips. Becomes derivable from video_people once
transcript-boosted people detection fills coverage (≥2 non-family people).
Until then, this file accumulates human-confirmed members.*

## Confirmed by Lara
- "Winter Camping in a Quinzee City" — the quinzee friend group
- "Winter Camping for the First Time" — same early friend era
- (mentioned generally: the insane freezing hot-tent trip, some Montana trips —
  exact video ids TBD when browsing with better people data)

## Implementation sketch
- Candidate query: videos with ≥2 video_people links excluding Matthew and
  family (Mom/Dad/Brother) → review queue, same pattern as series candidates.
- Transcript mining adds: names spoken aloud that aren't in descriptions.

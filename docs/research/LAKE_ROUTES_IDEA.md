# Lake Routes — BWCA trip mapping from transcripts

*Lara's idea, 2026-08-24. Status: design note, blocked on the improved
transcript corpus (Whisper pass). File under "eventually amazing."*

## The idea

For Boundary Waters trips, mine transcripts for lake-name mentions
("[Foo] Lake" / "Lake [Foo]"), timestamp them, and human-review whether he's
**on** the lake vs **talking about** it. He sometimes shows a full map view
and narrates the whole route — those moments are route gold. Chain the
confirmed on-lake stays into a per-video (or per-trip) lake sequence, then
eventually render little route maps to accompany videos.

## Pipeline sketch

1. **Gazetteer:** BWCA lake list (USGS GNIS covers Minnesota lake names with
   lat/lon; OSM has polygons). Load into a `lakes` table (name, aliases,
   lat, lon, gnis_id). Constrains matching to real lakes — "Snowbank Lake"
   matches, "that lake" doesn't.
2. **Mention extraction:** scan transcript_segments for gazetteer names with
   fuzzy tolerance (ASR mangles: "Insula" → "insula/in sula"). Emit
   (video_id, lake, start_seconds, segment text) rows → `lake_mentions`
   table, status unreviewed.
3. **Review queue** (the existing /admin framework): card = video + timestamp
   deep-link (watch the actual moment!) + segment text + proposed lake.
   Decisions: `on-lake` / `mentioned-only` / `route-narration` (the map-view
   moments — flag specially, they describe the WHOLE route at once).
4. **Route assembly:** per trip, order confirmed on-lake stays by video
   sequence + timestamp → lake chain (Snowbank → Disappointment → Ahsub...).
5. **Little maps:** static SVG/leaflet per trip — lake polygons/points from
   OSM, the route chain drawn through them, clips linked at each stop.
   Could live on trip pages.

## Notes

- Portage mentions ("the portage into X") are directional evidence — capture
  the preceding lake context.
- Entry point numbers ("entry point 30") are strong route anchors — BWCA
  entry points are a small known list; add to gazetteer.
- Whisper with a gazetteer-seeded initial_prompt should transcribe lake names
  far better than YouTube ASR — another reason this waits for the bake-off.
- Same machinery generalizes to Isle Royale (named campsites!) and Montana
  trips later.

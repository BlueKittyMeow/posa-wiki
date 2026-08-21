# People/Dog Attribution & Scraping Pipeline Audit

*Research report, 2026-08-20 (read-only survey of scripts + live DB queries).
Feeds the "keep current with new uploads" script design.*

## Q1 — How people/dogs got identified, and how well it worked

### The 3-stage one-shot pipeline (not part of the live app)

1. **`mine_video_descriptions.py`** — regex-mines `videos.description` for known entities.
   Hardcoded alias dicts (lines 12–45): people = matthew, lucas, funk, erin, ken, jake,
   mom, dad, brother; dogs = monty, rueger, frodo. Three confidence tiers:
   high ("with X" / "X joins me" patterns + multi-word substring checks),
   medium (family terms), low (capitalized-word scan).

   **⚠️ VERIFIED BUG:** every word-boundary check is written `r'\\b'` instead of
   `r'\b'` (e.g. line 112). As a regex that means literal-backslash-then-b, which
   never matches prose. Consequence: the single-word "mentioned" branch, ALL of
   medium-confidence, and ALL of low-confidence are dead code. Confirmed by the
   output file: `medium_confidence` and `low_confidence` are empty lists.
   **Erin never matched anything** (her name only ever appears as a bare word) —
   she has a people row but 0 video links, purely from this bug.

2. **`populate_people_dogs.py`** — reads only `high_confidence` from the mining JSON,
   maps names → DB ids via hardcoded dicts, INSERT OR IGNORE into video_people /
   video_dogs. Only Monty + Rueger are in dogs_mapping; **Layla (dog_id=3) is absent
   from the mapping entirely** → 0 links, unpopulatable by this pipeline.

3. **Tag authority path (separate mechanism):** `tag_authority_seed.py` /
   `revalidate_database_tags.py` validate people/dog *names* as tag authorities into
   `videos.validated_tags` from YouTube tags — this never feeds the junction tables.

### Coverage measured against the live DB (358 videos)

- ≥1 person link: 328/358 · ≥1 dog link: 64/358 · zero of either: 27
- People: Matthew 322 (≈36 videos missing even the host — mining is lossy),
  Lucas 17, Funk 7, Jake 6, Brother 2, Dad 1, Mom 1, Ken 1, **Erin 0**
- Dogs: Monty 62, Rueger 4, **Layla 0**
- validated_tags non-empty: 305/358 · unvalidated_tags non-empty: 278/358
- Tag validation = lowercase alias→canonical lookup against
  `tag_authority_system.json`; `review_unvalidated_tags.py` is the read-only
  "suggest new authorities" reporter.
- `docs/research/TAG_AUTHORITY_ARCHITECTURE.md` proposes migrating the JSON
  authority file into real DB tables (not yet implemented).

## Q2 — Scraping/import pipeline (for the keep-current script)

### API key
All scrapers read a plaintext **`api.md`** in repo root (gitignored, and **currently
missing from the working tree** — must be recreated before any new scrape). No env
var path exists.

### Endpoints (YouTube Data API v3)
- `channels?forHandle=MatthewPosa` → channel id + video count
- **Uploads playlist** via `playlistItems` (UC→UU prefix swap) — the CORRECT complete
  method (`complete_scraper.py`). The Search-API method (`full_scraper.py`) silently
  dropped 19 videos (94.7% coverage) per `API_SCRAPING_LESSONS.md` — do not use.
- `videos?part=snippet,contentDetails,statistics` batched 50 ids at a time.
- Rate limiting = bare `time.sleep(0.1–0.5)`; no backoff/retry/quota tracking.
- Scrapes write timestamped JSON dumps; DB import is a separate step.

### Import path
`import_videos.py` (bulk, hardcoded scrape filename) / `import_missing_videos.py`
(delta by video_id) both: parse ISO duration → formatted string, validate tags,
INSERT (OR REPLACE) into `videos` — **only the 12 core columns**. Junction tables,
trips/series, locations are all populated by separate manual one-off scripts.
`fix_missing_episodes.py` = hardcoded Unsuccessful-Fishing-Show-only episode
assigner (regex on title → video_versions rows).

### FTS
`build_fts_index.py` installs AFTER INSERT/UPDATE/DELETE triggers on `videos`
(**confirmed present in the live DB**) — new video rows auto-index into
`videos_fts`; no rebuild needed on incremental import.

### Freshness
`MAX(upload_date)` = **2025-06-08** ("Dog Update"). DB is ~14 months stale.

### Keep-current script requirements (derived)
1. Uploads-playlist delta fetch (newer than current MAX upload_date, walk playlist
   pages until overlap with known ids).
2. Insert via the import pattern, INCLUDING `duration_seconds` (post-008 migration).
3. Run description-mining + people/dog population for new rows (with the `\b`
   regex bug FIXED and Layla added to the mapping).
4. Auto-assign episodes for recognizable episodic titles (Unsuccessful Fishing
   Show pattern; extensible).
5. FTS handled by existing triggers; report a summary of what was added.
6. Read API key from env var with `api.md` fallback, so the server copy can use
   an env file instead of a stray plaintext file.

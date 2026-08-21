# scripts/archive/

One-off / superseded scripts, kept for reference. None of these are
imported by anything else in the repo (verified before archiving) — they
were run manually, once, at some point in the project's history.

- **analyze_dataset.py** — early exploratory analysis of the full scraped
  dataset (patterns for schema improvements and authority control).
- **analyze_trips.py** — early trip/series detection analysis over the DB.
  Superseded in effect by the current `/series` and `/trips` routes in
  `app.py`.
- **investigate_missing_videos.py** — one-off investigation of videos
  missing from the channel scrape (Shorts, live streams, premieres).
- **multi_authority_example.py** — worked example / scratch file for how
  multi-authority tag mapping could work for compound tags. Never wired
  into the real pipeline.
- **test_api.py** — early smoke test of YouTube Data API access (channel
  info + 10 oldest videos). Superseded by the real import scripts and
  `tests/`.
- **test_chapters_captions.py** — early exploratory test of YouTube
  chapters/auto-caption extraction.
- **full_scraper.py** — first full-channel scraper implementation.
  **Superseded by `complete_scraper.py`** (see
  `docs/research/API_SCRAPING_LESSONS.md`), which uses the uploads
  playlist instead and is the version still in active use at the repo
  root.
- **import_trips.py** — imported detected trips into the database
  (validation + trip record creation, linking video parts together). This
  was the import step that used the analysis from `analyze_trips.py`.
- **separate_series_trips.py** — the untracked one-off script that added
  `trips.series_type` and backfilled it, run directly against
  `posa_wiki.db`. It is why the column exists in the live database despite
  never having a tracked migration. **Now superseded by
  `migrations/009_add_trips_series_type.sql`**, which codifies the schema
  change for a from-scratch database build. Kept here for the
  categorization logic, in case the classification heuristics are ever
  needed again.

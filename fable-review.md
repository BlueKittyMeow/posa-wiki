# Fable Review — Codebase Findings & Metadata Roadmap Sketches

*A review of the Posa Wiki codebase (2026-07), plus design sketches for
transcript ingestion, faceted browsing, and the duration fix. Written as a
working document — each sketch is meant to be lifted into an implementation
session.*

---

## Part 1: Codebase Review Findings

### The good news

The fundamentals are solid and don't need rework:

- **Security basics are done correctly.** CSRF via Flask-WTF, passwords hashed
  with werkzeug, all SQL parameterized (no injection paths found), no `|safe`
  filters in templates (no XSS holes), and `ProductionConfig.init_app` refuses
  to boot with the default `SECRET_KEY`.
- **The schema design is ahead of the app.** `schema.md` already models
  multi-membership series, people/dog/location relationships with roles, and a
  references (Posaism) system with timestamp fields. Most of Part 3 of this doc
  is "populate and surface what's already designed," not new modeling.
- **Docs show good self-awareness** — the roadmap in `PROJECT_STATUS.md` and
  `todo.md` already names most of the right next steps.

### Reliability issues

1. **DB connections are not leak-safe.** Every route does
   `conn = get_db_connection()` … `conn.close()` manually with no `try/finally`.
   Any exception mid-route leaks the connection. Fix: the standard Flask
   pattern — open on `g`, close in a `teardown_appcontext` handler:

   ```python
   from flask import g

   def get_db():
       if 'db' not in g:
           g.db = sqlite3.connect(app.config['DATABASE_PATH'])
           g.db.row_factory = sqlite3.Row
       return g.db

   @app.teardown_appcontext
   def close_db(exception=None):
       db = g.pop('db', None)
       if db is not None:
           db.close()
   ```

   This also removes the duplicated `get_db_connection()` (one copy in
   `app.py`, another in `blueprints/auth.py`) and all the manual `conn.close()`
   calls sprinkled through routes.

2. **Detail routes bypass the custom 404 page.** `video_detail`,
   `person_detail`, `dog_detail`, and `trip_detail` return raw
   `"Video not found", 404` strings instead of `abort(404)`, so the
   `errors/404.html` page registered with `@app.errorhandler(404)` never
   renders for missing entities. One-line fix per route: `abort(404)`.

3. **Duration sorting is broken** — detailed in Part 2 because the fix
   overlaps with the metadata work.

4. **No login throttling.** Fine for a private site; add Flask-Limiter on
   `/auth/login` before this ever faces the public internet.

### Repo hygiene

- **~8 MB of one-off scrape JSON is committed** (`full_channel_scrape_*.json`,
  `complete_channel_scrape_*.json`, etc.). These are regenerable data dumps,
  not source. Move to a gitignored `data/` directory (history rewrite optional
  — the bloat is modest, stopping the growth matters more).
- **24 loose scripts at repo root** with no indication of which are live tools
  vs. historical one-shots. Suggest `scripts/` (live: `build_fts_index.py`,
  `run_migration.py`) and `scripts/archive/` (one-shots: `fix_missing_episodes.py`,
  `investigate_missing_videos.py`, `separate_series_trips.py`, …) with a short
  README in each.
- **Documentation sprawl**: `README.md` and `README-FLASK.md` are ~80%
  duplicated; there are two *different* `debug-2a.md` files (root and `docs/`);
  `DOCUMENTATION_CONSOLIDATION.md` is a stale meta-doc about a past cleanup.
  Worth one consolidation pass: single README, everything phase-related under
  `docs/`.
- **Migrations are inconsistent.** Only `003_create_users_table.sql` exists;
  the rest of the schema lives in `create_database.py`. Before the planned
  SQLAlchemy/Alembic move, at minimum keep every schema change as a numbered
  SQL file so there's a replayable history. (The migrations sketched in this
  doc follow that convention: 004, 005, …)

### Testing

`PROJECT_STATUS.md` claims a pytest/pytest-flask strategy, but no pytest exists
anywhere (not in `requirements.txt`, no automated tests). `test_api.py` and
`test_chapters_captions.py` are manual exploration scripts that hit the live
YouTube API. The most valuable starter suite is small: a fixture that builds an
in-memory SQLite DB from the schema, then smoke-tests every route for 200/404
and asserts sort orders. That would have caught both the duration bug and the
raw-404 issue.

### Minor

- `requirements.txt`: `Flask-Paginate` unpinned; `requests` (used by every
  scraper) missing entirely; nothing for the future transcript work yet.
- The sidebar `context_processor` runs two queries on every request including
  error pages. Cheap at current scale; memoize if the data grows.
- No `.env.example` documenting expected environment variables
  (`FLASK_SECRET_KEY`, `DATABASE_PATH`, `POSA_WIKI_ENV`, per-page settings).

---

## Part 2: The Duration Bug (fix first — small, user-visible)

`videos.duration` stores raw ISO 8601 strings (`PT4M19S`). Two consequences:

1. **`/videos?sort=duration` is lexicographic garbage** — `ORDER BY duration`
   on strings sorts `PT9M` *after* `PT10M`, `PT1H…` before `PT2M…`, etc.
2. **`format_duration()` in `app.py` can't handle hours.** For `PT1H23M45S`,
   `int('1H23')` raises, the bare `except` swallows it, and the raw ISO string
   renders in the UI. Matthew's hour-plus videos display as `PT1H23M45S`.

### Fix sketch

**Migration** (`migrations/004_add_duration_seconds.sql`):

```sql
ALTER TABLE videos ADD COLUMN duration_seconds INTEGER;
CREATE INDEX IF NOT EXISTS idx_videos_duration_seconds
    ON videos(duration_seconds);
```

**Parser + backfill** (`scripts/backfill_duration_seconds.py`):

```python
import re, sqlite3

ISO_DURATION = re.compile(
    r'^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$'
)

def iso_to_seconds(value):
    m = ISO_DURATION.match(value or '')
    if not m:
        return None
    h, mins, s = (int(g) if g else 0 for g in m.groups())
    return h * 3600 + mins * 60 + s

conn = sqlite3.connect('posa_wiki.db')
rows = conn.execute(
    'SELECT video_id, duration FROM videos WHERE duration_seconds IS NULL'
).fetchall()
for video_id, duration in rows:
    conn.execute(
        'UPDATE videos SET duration_seconds = ? WHERE video_id = ?',
        (iso_to_seconds(duration), video_id),
    )
conn.commit()
print(f'Backfilled {len(rows)} rows')
```

**App changes:**

- `video_list`: map `sort=duration` to `ORDER BY duration_seconds`.
- Replace the string-munging `format_duration` with a seconds-based formatter:

```python
def format_duration(seconds):
    if seconds is None:
        return 'Unknown'
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'
```

- Import scripts (`import_videos.py` etc.) should populate `duration_seconds`
  at insert time so the backfill never needs re-running.

This is also a prerequisite for a duration facet later ("overnights" vs.
"10-day epics").

---

## Part 3: Transcript Ingestion (the highest-value unused data)

### Findings

- `chapters_captions_test.json` shows **all 5 sampled videos have English
  auto-generated (`asr`) caption tracks** — coverage across the full 358 is
  likely near-total.
- **The YouTube Data API cannot download caption content** with an API key.
  `captions.download` requires OAuth as the channel owner; the key can only
  *list* tracks (which is what the existing test script does).
- Practical route: **`youtube-transcript-api`** (or yt-dlp), which fetches the
  ASR track without auth. 358 videos is a small one-time batch — rate-limit
  politely (a few seconds between requests) and cache results to disk so a
  re-run never re-fetches.
- **Chapters are a dead end.** The test found zero timestamp chapters in
  descriptions, and the API doesn't expose player chapters at all. Transcripts
  cover the same need better.
- **ASR quality caveat:** no punctuation, and names get mangled ("Rueger" will
  surface as "Ruger"/"Rooker"). Anything matching against transcript text
  (especially Posaism detection) must be fuzzy, and auto-detected results
  should land in an *unvalidated* state for human review — same pattern as the
  existing validated/unvalidated tag split.

### Schema sketch (`migrations/005_create_transcripts.sql`)

```sql
-- One row per caption segment, timestamped
CREATE TABLE transcript_segments (
    segment_id INTEGER PRIMARY KEY,
    video_id VARCHAR NOT NULL REFERENCES videos(video_id),
    start_seconds REAL NOT NULL,
    duration_seconds REAL,
    text TEXT NOT NULL
);
CREATE INDEX idx_transcript_segments_video
    ON transcript_segments(video_id, start_seconds);

-- Ingestion bookkeeping: know what's fetched, what failed, what has no track
CREATE TABLE transcript_status (
    video_id VARCHAR PRIMARY KEY REFERENCES videos(video_id),
    status VARCHAR NOT NULL,          -- 'fetched', 'no_captions', 'error'
    language VARCHAR,                 -- 'en'
    track_kind VARCHAR,               -- 'asr' or 'manual'
    fetched_at TIMESTAMP,
    error TEXT
);

-- Separate FTS index so transcript hits rank apart from title/description
CREATE VIRTUAL TABLE transcripts_fts USING fts5(
    text,
    content='transcript_segments',
    content_rowid='segment_id'
);
```

### Ingestion script sketch (`scripts/fetch_transcripts.py`)

```python
"""Fetch ASR transcripts for all videos. Idempotent and resumable:
skips any video already marked in transcript_status."""
import sqlite3, time
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled, NoTranscriptFound,
)

DELAY_SECONDS = 3          # be polite; ~20 min total for 358 videos

conn = sqlite3.connect('posa_wiki.db')
pending = conn.execute('''
    SELECT v.video_id FROM videos v
    LEFT JOIN transcript_status ts ON v.video_id = ts.video_id
    WHERE ts.video_id IS NULL
''').fetchall()

for (video_id,) in pending:
    try:
        segments = YouTubeTranscriptApi.get_transcript(
            video_id, languages=['en'])
        conn.executemany(
            '''INSERT INTO transcript_segments
               (video_id, start_seconds, duration_seconds, text)
               VALUES (?, ?, ?, ?)''',
            [(video_id, s['start'], s['duration'], s['text'])
             for s in segments],
        )
        conn.execute(
            '''INSERT INTO transcript_status
               (video_id, status, language, track_kind, fetched_at)
               VALUES (?, 'fetched', 'en', 'asr', CURRENT_TIMESTAMP)''',
            (video_id,),
        )
    except (TranscriptsDisabled, NoTranscriptFound):
        conn.execute(
            '''INSERT INTO transcript_status (video_id, status, fetched_at)
               VALUES (?, 'no_captions', CURRENT_TIMESTAMP)''',
            (video_id,),
        )
    except Exception as exc:
        conn.execute(
            '''INSERT INTO transcript_status
               (video_id, status, error, fetched_at)
               VALUES (?, 'error', ?, CURRENT_TIMESTAMP)''',
            (video_id, str(exc)),
        )
    conn.commit()
    time.sleep(DELAY_SECONDS)
```

Then populate FTS (mirroring `build_fts_index.py`):

```sql
INSERT INTO transcripts_fts(rowid, text)
SELECT segment_id, text FROM transcript_segments;
```

### What transcripts unlock

1. **Timestamped search.** Search results deep-link to the exact moment:
   `https://www.youtube.com/watch?v={video_id}&t={int(start_seconds)}s`.
   Rank title matches > description matches > transcript matches so transcript
   hits enrich rather than pollute results:

   ```sql
   -- Transcript search with per-video best hit
   SELECT v.video_id, v.title,
          ts.start_seconds, ts.text,
          MIN(rank) AS best_rank
   FROM transcripts_fts f
   JOIN transcript_segments ts ON ts.segment_id = f.rowid
   JOIN videos v ON v.video_id = ts.video_id
   WHERE transcripts_fts MATCH ?
   GROUP BY v.video_id
   ORDER BY best_rank
   ```

2. **Semi-automatic Posaism detection.** The `references` /
   `video_references` tables already have `timestamp` and
   `is_first_appearance` fields sitting empty. A scanner that fuzzy-matches
   each reference's name/variants against transcript segments (e.g.
   `rapidfuzz.partial_ratio` over a sliding window of joined segments) can
   populate candidate appearances across the whole catalog — first
   appearances, recurrence counts, all of it. Candidates land unvalidated;
   the Phase 2B edit UI promotes them.

3. **Better facet derivation** — see Part 4; night counts, weather, and
   activities are all *said out loud* in videos even when absent from
   descriptions.

---

## Part 4: Intelligent Sorting = Faceted Browsing

### The reframe

"Sort by type of adventure / people involved" is really *filtering*, and the
schema already models it: multi-membership `series` with `series_type`
(activity/location/content/special), `video_people`, `video_dogs`,
`locations`, and manual fields for `season` / `number_of_nights` / `weather`.
The gap is (a) those fields are mostly unpopulated and (b) the UI only sorts.

At 358 rows this is plain SQL with joins — no search engine, no denormalized
facet tables needed.

### Facet UI sketch

`/videos` grows filter parameters, stackable:

```
/videos?activity=winter-camping&dog=monty&nights_min=3&sort=duration
```

Query composition pattern (all params optional, all parameterized):

```python
query = '''
    SELECT DISTINCT v.* FROM videos v
    LEFT JOIN video_series vs ON v.video_id = vs.video_id
    LEFT JOIN video_dogs   vd ON v.video_id = vd.video_id
    WHERE 1=1
'''
params = []
if activity_series_id:
    query += ' AND vs.series_id = ?'
    params.append(activity_series_id)
if dog_id:
    query += ' AND vd.dog_id = ?'
    params.append(dog_id)
if nights_min:
    query += ' AND v.number_of_nights >= ?'
    params.append(nights_min)
```

UI: filter chips above the video grid showing active facets (each with an ×),
plus dropdowns/sidebar sections for activity, location, people, dogs, season,
and duration buckets (`< 30 min`, `30–60`, `1 h+` — needs `duration_seconds`
from Part 2). Facet options should show counts
(`Winter Camping (47)`) — one `GROUP BY` query per facet type.

### Facet population pipeline

Derivations, in confidence order, all landing **unvalidated** for review:

| Facet | Source | Method |
|---|---|---|
| Nights | title, description, transcript | Regex: `(\d+)\s*(?:day|night)s?\b`, `overnight` → 1 |
| Season | title + youtube_tags keywords | Keyword map (`winter camping`, `snowstorm`, `ice` → winter, …). *Not* upload date — upload lag makes dates lie. |
| Activity series | youtube_tags via existing tag-authority aliases | The `tag_authority_system.json` alias mappings already do this normalization |
| Weather | transcript + description | Keyword map, lowest confidence |

Suggested pattern to match the existing validated/unvalidated tag split: add a
`facet_candidates` table (`video_id`, `facet_type`, `value`, `source`,
`confidence`, `status`) rather than writing directly to `videos` columns; a
review screen promotes candidates into the real columns/junction tables.

---

## Part 5: Suggested Order of Work

1. **Duration fix** (Part 2) — an afternoon; user-visible; unblocks duration
   facet. Pairs naturally with the `abort(404)` and `g`-based connection
   fixes from Part 1 since all three touch `app.py`.
2. **Transcript ingestion** (Part 3) — the schema, fetch script, and FTS
   index. Everything downstream depends on it.
3. **Facet derivation pipeline** (Part 4) — nights/season/activity candidates
   into review flow.
4. **Faceted browse UI + timestamped search results.**
5. **Posaism fuzzy-matching** over transcripts feeding `video_references`.

Independent, anytime: repo hygiene batch (scrape JSONs out of git, scripts
into folders, doc consolidation) and the pytest starter suite.

### Requirements additions when this work starts

```
youtube-transcript-api>=0.6
rapidfuzz>=3.0        # Posaism fuzzy matching (step 5)
pytest>=8.0           # dev
pytest-flask>=1.3     # dev
```

---

*Caveat: the live SQLite DB is gitignored, so population state of
`locations`, `video_locations`, and the manual curation fields was inferred
from code and docs, not inspected. If some are already populated, Part 4's
step 3 shrinks accordingly.*

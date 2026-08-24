# Keeping the catalog current

`scripts/update_catalog.py` is the incremental updater: it pulls new uploads from
the YouTube Data API, inserts them, and runs the enrichment that used to be a
pile of one-off scripts. It is safe to run repeatedly — a second run in a row
inserts nothing.

## API key

Two sources, checked in order:

1. `YOUTUBE_API_KEY` environment variable (preferred, especially on a server).
2. `api.md` at the repo root — the historical location, gitignored, plain text.

If neither exists the script exits 1 with a clear message. The key is never
printed.

## Running it locally

```bash
# always look before you leap
YOUTUBE_API_KEY=... ./venv/bin/python scripts/update_catalog.py --dry-run

# for real
YOUTUBE_API_KEY=... ./venv/bin/python scripts/update_catalog.py
```

Flags:

| Flag | Effect |
|------|--------|
| `--dry-run` | Prints what would be inserted; writes nothing (transaction rolled back). |
| `--full-scan` | Walks the entire uploads playlist instead of stopping at the first page of all-known ids. Use after a suspected gap. |
| `--refresh-stats` | Also updates `view_count` / `like_count` on videos already in the DB (implies a full playlist walk). Off by default because it costs quota. |
| `--db PATH` | Point at a different SQLite file (used by the tests). |
| `--handle NAME` | Channel handle, defaults to `MatthewPosa`. |
| `--quiet` | Less per-item chatter. |

Every run ends with a summary: new videos, people/dog links added, episodes
assigned, and the number of unvalidated tags on the new rows (review those with
`review_unvalidated_tags.py`).

## What actually runs on Factotum (deployed 2026-08-24)

The key lives in `/srv/posa-wiki/.env` (`YOUTUBE_API_KEY=...`, chmod 600),
which doubles as the systemd `EnvironmentFile`. Three timers, all
`Persistent=true` (missed fires catch up on boot):

| Unit | Cadence | Does |
|---|---|---|
| `posa-catalog.timer` | weekly, Sun 23:30 | `update_catalog.py` → `assign_series.py` → `derive_seasons.py` (three sequential ExecStart lines in one oneshot service) |
| `posa-archive.timer` | **daily during backfill**; drop to monthly once caught up | `scripts/archive_channel.sh` — channel backup to `/mnt/media6t/archive/posa/` |
| `posa-transcripts.timer` | daily | `ingest_transcripts.py` — new subtitle sidecars → transcript search |

Check any of them with `sudo journalctl -u posa-<name>.service` (sudo — the
non-root session bus quirk on Factotum makes bare `systemctl` whine).

**Archive pacing (learned 2026-08-21):** a continuous multi-hour yt-dlp session
got the Pi's IP bot-flagged by YouTube ("Sign in to confirm you're not a bot",
every video failing thereafter). `archive_channel.sh` therefore runs capped
(`--max-downloads 50`, exit code 101 = success) with randomized 20–90 s sleeps
between videos, daily. Do NOT "fix" a stall by removing the pacing, and do not
reach for `--cookies` — that would tie a real YouTube account to bulk
downloading. If a run fails with bot-check errors, just let the next daily run
retry; the block is IP-temporary and `.archive.txt` makes every run resumable.

Back up `posa_wiki.db` before first runs of anything new (`cp posa_wiki.db
posa_wiki.db.bak.<reason>` — `*.bak*` is gitignored).

## What it does automate

- Uploads-playlist delta discovery (`UC` → `UU` prefix swap, `playlistItems`
  paginated 50/page, newest-first, stops at the first page of all-known ids).
  Never the Search API — see `docs/research/API_SCRAPING_LESSONS.md`.
- `videos` INSERT with the same column mapping as `import_missing_videos.py`,
  including `duration_seconds` and the `youtube_tags` /
  `validated_tags` / `unvalidated_tags` split against
  `tag_authority_system.json`. **INSERT only, never REPLACE** — curated columns
  on existing rows are never touched (except the counters, and only under
  `--refresh-stats`).
- Description mining for new rows (`mine_video_descriptions.analyze_description`)
  and the resulting `video_people` / `video_dogs` junction rows
  (`populate_people_dogs.link_entities`).
- Episode auto-assignment for recognised episodic series. **As of 2026-08-20 this
  writes to `video_series` against the `series` table**, not to
  `trips`/`video_versions` — the `series` table is the source of truth for
  thematic groupings and shows, and `trips` is reserved for genuine multi-part
  trips. The `PATTERNS` list at the top of the script maps a title regex →
  `series.name`; adding a future series is one entry. Currently: *Unsuccessful
  Fishing Show*.
- FTS: nothing to do — the `videos_ai` / `videos_au` / `videos_ad` triggers keep
  `videos_fts` in sync. The script verifies they exist and warns (suggesting
  `build_fts_index.py`) if they don't. It never rebuilds the index for you.

## After an update run: reassign series and derive seasons

`scripts/update_catalog.py` only handles the numbered episodic patterns. Rerun
the broader thematic rules afterwards:

```bash
python scripts/seed_series.py     # only needed if the taxonomy changed
python scripts/assign_series.py   # title/tag rules -> video_series
python scripts/derive_seasons.py  # title/tag rules -> videos.season
```

All three are idempotent — a second run inserts nothing. `assign_series.py` writes
high-confidence memberships only, stamping `video_series.notes` with the rule
that fired (`auto:title-pattern`, `auto:tag-match`, `auto:episode-pattern`,
`auto:implied-by-child`) so provenance stays queryable. Medium-confidence
guesses go to `data/series_review_candidates.json` for a human pass and are
never written to the database.

### Seasons

`scripts/derive_seasons.py` fills `videos.season` from the same kind of
evidence, with provenance in `videos.season_confidence` / `videos.season_source`
(migration `011`). Seasons are a **video facet, not a series**, and three rules
govern it:

- **Unknown (NULL) is a legitimate value.** Most of the catalogue has no season
  evidence, and the script never guesses to fill the column. A video that
  matches two seasons is a *conflict* and is left Unknown.
- **Upload date is not evidence.** Uploads lag filming badly, especially for
  the early videos — several winter trips were published in April.
- **A human decision is untouchable.** `season_confidence = 'human'` is never
  overwritten, and an existing high-confidence value is only re-derived when
  the season is currently NULL.

Medium-confidence guesses (holiday titles, description keywords, the
`winter camping` YouTube tag) go to `data/season_review_candidates.json` and
are clicked through at `/admin/review/seasons`. Approving stamps
`season_confidence = 'human'`; rejecting means "Unknown stands" and the video
is never proposed again (decisions persist in
`data/season_review_decisions.json`).

Note on the `winter camping` tag: it is copy-pasted channel SEO boilerplate
(130 videos carry it; 37 of them share one identical 44-tag block, and it sits
on canoe trips and anniversary compilations), so it only *proposes* winter
rather than writing it. `TRUST_WINTER_TAG` at the top of the script flips that
back to a high-confidence write if the owner ever decides otherwise.

```bash
python scripts/derive_seasons.py --dry-run   # counts only, writes nothing
python scripts/derive_seasons.py             # apply + regenerate the queue
```

## Transcripts

`scripts/ingest_transcripts.py` turns the subtitle sidecars written by the
yt-dlp channel archive (`scripts/archive_channel.sh`) into searchable text. It
reads files, never the network — no API key, no quota.

Each archived video has a WebVTT sidecar beside its media file:

```
/mnt/media6t/archive/posa/<dirname>/<title> [<video_id>].en.vtt
```

The video id is the last `[...]` group in the filename; `.en.vtt` wins over
`.en-orig.vtt` when a video has both.

```bash
# look first
./venv/bin/python scripts/ingest_transcripts.py --dry-run

# for real (defaults to /mnt/media6t/archive/posa and the repo posa_wiki.db)
./venv/bin/python scripts/ingest_transcripts.py
```

| Flag | Effect |
|------|--------|
| `--archive-dir PATH` | Archive root to scan. Default `/mnt/media6t/archive/posa`. |
| `--db PATH` | Point at a different SQLite file (used by the tests). |
| `--redo VIDEO_ID` | Delete that video's segments + status row and re-parse it. |
| `--dry-run` | Parse and report; the transaction is rolled back. |
| `--quiet` | Less per-file chatter. |

It applies `migrations/010_create_transcripts.sql` itself if the transcript
tables are missing, so there is no separate migration step. Storage:

- `transcript_segments` — one row per spoken phrase (`video_id`,
  `start_seconds`, `duration_seconds`, `text`).
- `transcript_status` — one row per video: `ingested` / `no_captions` /
  `error`, plus `source` (`youtube-asr-vtt` today, `whisper-large-v3` later),
  `language`, `segment_count`, `ingested_at`.
- `transcripts_fts` — FTS5 mirror of the segment text, kept in sync by the
  `transcript_segments_ai` / `_au` / `_ad` triggers exactly like `videos_fts`.
  Nothing to rebuild by hand.

Idempotent: a video already in `transcript_status` is skipped, so re-running
after each archive pass only picks up new material.

**Order matters.** A sidecar whose video id is not yet in `videos` is reported
and skipped (never fatal, nothing written) — the catalog update has to run
first. The monthly flow on Factotum is:

```bash
YOUTUBE_API_KEY=... ./venv/bin/python scripts/update_catalog.py   # new rows in `videos`
./venv/bin/python scripts/assign_series.py                        # thematic series
./venv/bin/python scripts/derive_seasons.py                       # videos.season
./scripts/archive_channel.sh                                      # media + .en.vtt sidecars
./venv/bin/python scripts/ingest_transcripts.py                   # sidecars -> searchable text
```

The `/search` page queries `transcripts_fts` alongside `videos_fts` and shows
the matches under a "Spoken in videos" section, each linking to the moment on
YouTube (`?v=<id>&t=<seconds>s`).

Parsing note: YouTube's auto-generated captions are a *rolling* format — every
cue repeats the previous line and adds one new line carrying per-word
`<00:00:01.599><c>` timing tags. `parse_vtt()` strips that markup and collapses
the repeats so each phrase is stored once, at its earliest start time. If a
future caption source parses badly, that function (and
`tests/test_transcripts.py`, which runs it against real trimmed sidecars) is
where to look.

## What stays manual

- **Medium-confidence series membership.** Day Hiking and Backyard Adventures
  are proposal-only; approve them in `/admin/review/series` (Michigan
  Adventures was retired as a series 2026-08-20 — location stays a tag).
- **Multi-part trip membership.** A multi-part canoe trip with freeform titles
  will not be grouped automatically — assign it in the app or with
  `import_trips.py` / `separate_series_trips.py`.
- **Locations, number of nights, season, weather, series notes** — all curated
  fields, untouched by the updater.
- **New people or dogs.** Mining only knows the entities hardcoded in
  `mine_video_descriptions.load_known_entities()` and mapped in
  `populate_people_dogs.PEOPLE_MAPPING` / `DOGS_MAPPING`. A new companion needs a
  row in `people`/`dogs`, an alias entry, and a mapping entry.
- **Tag authority curation.** New unvalidated tags are stored but never promoted;
  `review_unvalidated_tags.py` reports candidates.

## Tests

`tests/test_update_catalog.py` exercises the whole delta → insert → mine → link →
episode path against a throwaway copy of `posa_wiki.db` with the API layer
monkeypatched, so it runs with no key and no network:

```bash
./venv/bin/python -m pytest tests/test_update_catalog.py -q
```

`tests/test_transcripts.py` does the same for transcripts: `parse_vtt()` against
the trimmed real sidecars in `tests/fixtures/`, a full ingest into a throwaway
database and archive tree, idempotency, and the `/search` transcript section.

```bash
./venv/bin/python -m pytest tests/test_transcripts.py -q
```

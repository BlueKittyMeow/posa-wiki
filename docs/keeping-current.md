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

## Running it on a server

Put the key in an environment file readable only by the service user:

```ini
# /etc/default/posa-wiki
YOUTUBE_API_KEY=AIza...
```

```ini
# /etc/systemd/system/posa-catalog-update.service
[Unit]
Description=Posa wiki catalog update

[Service]
Type=oneshot
User=posa
WorkingDirectory=/srv/posa-wiki
EnvironmentFile=/etc/default/posa-wiki
ExecStart=/srv/posa-wiki/venv/bin/python scripts/update_catalog.py
```

```ini
# /etc/systemd/system/posa-catalog-update.timer
[Unit]
Description=Monthly Posa wiki catalog update

[Timer]
OnCalendar=monthly
Persistent=true

[Install]
WantedBy=timers.target
```

`systemctl enable --now posa-catalog-update.timer`. Monthly is plenty for a
channel that posts weekly-ish; `Persistent=true` catches a missed fire if the
box was off. Check results with `journalctl -u posa-catalog-update.service`.

Back up `posa_wiki.db` before the first real server run.

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

## After an update run: reassign series

`scripts/update_catalog.py` only handles the numbered episodic patterns. Rerun
the broader thematic rules afterwards:

```bash
python scripts/seed_series.py     # only needed if the taxonomy changed
python scripts/assign_series.py   # title/tag rules -> video_series
```

Both are idempotent — a second run inserts nothing. `assign_series.py` writes
high-confidence memberships only, stamping `video_series.notes` with the rule
that fired (`auto:title-pattern`, `auto:tag-match`, `auto:episode-pattern`,
`auto:implied-by-child`) so provenance stays queryable. Medium-confidence
guesses go to `data/series_review_candidates.json` for a human pass and are
never written to the database.

## What stays manual

- **Medium-confidence series membership.** Day Hiking, Backyard Adventures and
  Michigan Adventures are proposal-only; promote them by hand from
  `data/series_review_candidates.json`.
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

# Project Status — Posa Wiki

**Updated: 2026-08-24.** Live at https://posa-wiki.bluekittymeow.com (public,
no auth; editing behind login). Runs on Factotum (gunicorn :8018, cloudflared).
Branch of record: `2b-dev`. Deploy = rsync working tree (exclude venv/.git/.env/
db/data) + `sudo systemctl restart posa-wiki`. See `docs/keeping-current.md`
for the automation runbook.

## What's live

- **Catalog:** 373 videos, full YouTube metadata, numeric duration sort,
  FTS5 search. Weekly self-update (`posa-catalog.timer` → update_catalog →
  assign_series → derive_seasons).
- **Series system** (multi-membership, series table is source of truth):
  activity/location/content/special types, episodic numbering (Unsuccessful
  Fishing Show, Christmas Story), 600+ memberships, `/series/<id>` pages.
  Retired: Spring/Fall Camping (seasons are a facet), Michigan Adventures
  (location is a tag).
- **Season facet:** high-confidence auto-derivation from titles (conflicts and
  holiday-inferences go to review; human values untouchable), filter chips on
  /videos, Unknown is legitimate.
- **Transcript search:** "Spoken in videos" section on /search with
  timestamped YouTube deep links. Segments ingest daily from the channel
  archive's subtitle sidecars (`posa-transcripts.timer`).
- **Admin review center** (`/admin`, editor login): four queues — series
  candidates, unvalidated tags (promote-to-authority), Layla-via-Lucas dog
  candidates, seasons. Decisions persist in `data/*_decisions.json` on the Pi
  (never in git, never clobbered by deploys); all actions audit-logged.
- **Watch page** (`/watch/<id>`): official YouTube embed (Premium ad-free +
  views count), tap-to-dim overlay (50/75/100% with audio continuing),
  night mode, keyboard shortcuts, prev/next episode, cast from phone Chrome.
- **Channel backup:** full-fidelity yt-dlp archive to `/mnt/media6t/archive/posa/`
  on Factotum (video + info.json + thumbnails + subtitles). Daily paced runs
  (50/run, randomized sleeps — YouTube bot-flags marathon sessions). ~1.0–1.2 TB
  when complete.

## Automation on Factotum

| Unit | Cadence | Purpose |
|---|---|---|
| `posa-wiki.service` | always | The site (gunicorn 127.0.0.1:8018) |
| `posa-catalog.timer` | weekly Sun 23:30 | New uploads → DB → series/seasons |
| `posa-archive.timer` | daily (backfill; monthly later) | Channel backup |
| `posa-transcripts.timer` | daily | Subtitle sidecars → transcript search |

## Test suite

`./venv/bin/python -m pytest tests/ -q` → 226 passed / 4 known pre-existing
failures (403-handler routing + 3 JWT auth tests — Phase 2B follow-up).

## Next up (roughly in order)

- Whisper vs Parakeet local ASR bake-off on MarshLair → replace YouTube ASR
  transcripts with better ones (names!), same tables via `source` column.
- Posaism detection + reference pages over the transcript corpus.
- BWCA lake-mention extraction → per-video lake routes → little maps
  (see `docs/research/LAKE_ROUTES_IDEA.md`).
- Friend-trips collection (`docs/research/FRIEND_TRIPS_SEED.md`) once people
  coverage improves.
- Entity CRUD forms (Phase 2B Step 3; service layer + forms already built).
- Faceted browse UI combining series/season/people/dogs/duration filters.
- Visual redesign pass (with faceted browse).
- Fix 4 pre-existing test failures.
- Teeny Trout channel indexing (separate future project).

## History

Phase 1 (browse UI) and Phase 2A (config, errors, CSRF, auth, pagination,
FTS) complete — see git history and `docs/`. Phase 2B step 1 complete
(blueprints, service layer, forms, JWT/rate-limit/audit security); Step 2
reshaped into the review center. `fable-review.md` (on `main`) was the
2026-07 audit that seeded the fix roadmap; `docs/research/` holds the
working analyses.

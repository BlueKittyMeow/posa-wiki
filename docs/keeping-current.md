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
| `posa-catalog.timer` | weekly, Sun 23:30 | `update_catalog.py` → `assign_series.py` → `derive_seasons.py` → `derive_nights.py` (four sequential ExecStart lines in one oneshot service) |
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
python scripts/derive_nights.py   # title rules -> videos.number_of_nights
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

### Trip length (nights)

`scripts/derive_nights.py` fills `videos.number_of_nights` from title
evidence, with provenance in `videos.nights_confidence` /
`videos.nights_source` (migration `012`). It is deliberately the same shape as
`derive_seasons.py`, and the same three rules govern it:

- **Unknown (NULL) is a legitimate value**, and **0 is never inferred**. A
  Hike and Cook is *probably* a day trip, but "probably" is a review-tier
  answer — day-trip series membership only ever *proposes* 0 nights.
- **A title stating a length is exact.** "7 Nights Of Winter Camping" → 7;
  the part-title form "(Night 3 of 7)" gives the trip length 7, not 3;
  "Overnight"/"Overnighter" → 1.
- **Days convert, `nights = days - 1`** (owner-approved, and validated against
  his own titles: "8 Day Wilderness Adventure with My Dog (Night 7 of 7)"
  pairs an 8-day framing with a 7-night one). A title carrying both forms is
  cross-checked — consistent writes, **inconsistent goes to review** and is
  never auto-written.
- **A human decision is untouchable** (`nights_confidence = 'human'`), and an
  existing value is only re-derived when `number_of_nights` is NULL.

Medium-confidence guesses — week language ("Weeklong", "A Week in the
Wilderness": 6 or 7 nights, the title does not say which), day-trip series
membership, description keywords, and inconsistent day/night pairs — go to
`data/nights_review_candidates.json` and are clicked through at
`/admin/review/nights`. Approving stamps `nights_confidence = 'human'`;
rejecting means "Unknown stands" (decisions persist in
`data/nights_review_decisions.json`).

```bash
python scripts/derive_nights.py --dry-run   # counts only, writes nothing
python scripts/derive_nights.py             # apply + regenerate the queue
```

First run over 358 videos: 91 written (33 overnights, 26 seven-nighters, the
rest spread from 2 to 14), **267 unknown**, 65 review candidates. A second run
writes 0.


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
./venv/bin/python scripts/derive_nights.py                        # videos.number_of_nights
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

## Whisper re-transcription + adjudication (`scripts/pipeline/`)

The YouTube auto-captions above are witness #2. The transcript of record is a
**faster-whisper large-v3** re-transcription, adjudicated against the YouTube
track by a local LLM judge and then reviewed by a human where the judge could
not decide. The configuration is the one the adjudicator tournament settled
(`docs/research/TRANSCRIPT_VERIFICATION_DESIGN.md` → *PRODUCTION CONFIG*;
evidence in `TOURNAMENT_RESULTS.md`):

| | |
|---|---|
| Witnesses | Whisper large-v3 (prompted, word timestamps) **+ YouTube ASR**. Parakeet is **not** run — adding it dropped the hard-error fix rate 46 % → 26 %. |
| Judge | `mistral-small3.2:24b` on MarshLair's agent ollama store, `full` packet (style card v1.1 + entity roster + disagreement flags). Understudy `qwen3.5:35b-a3b` (≈equal, 3× faster) via `--model`. |
| Banned | `bare` packets — no card, no lexicon, no flags made the transcript *worse* (WER +0.176). |
| Appellate | **A human**, via `/admin/review/transcripts`. No audio judge: none produced a single correction. |

### The three scripts

```bash
# 1. transcribe  (MysteryOfGlass driver, GPU work on MarshLair)
./venv/bin/python scripts/pipeline/transcribe_batch.py --status
./venv/bin/python scripts/pipeline/transcribe_batch.py            # all remaining
./venv/bin/python scripts/pipeline/transcribe_batch.py --limit 3  # a few

# 2. judge  (MysteryOfGlass, drives ollama over the :11435 tunnel)
./venv/bin/python scripts/pipeline/judge_batch.py --status
./venv/bin/python scripts/pipeline/judge_batch.py

# 3. apply  (on Factotum, where the archive and the DB live)
ssh bluekitty@192.168.1.201
cd /srv/posa-wiki
cp posa_wiki.db posa_wiki.db.bak.whisper          # always, before the first run
./venv/bin/python scripts/pipeline/apply_verdicts.py --dry-run
./venv/bin/python scripts/pipeline/apply_verdicts.py --require-verdicts
```

Where things land:

| Path | What |
|---|---|
| `/mnt/media6t/archive/posa/transcripts_whisper/<id>.whisper.json` | segments + per-word probabilities (the record) |
| `/mnt/media6t/archive/posa/transcripts_verdicts/<id>.verdicts.json` | the judge's sentence-level rulings |
| `data/pipeline/*.jsonl` | the two ledgers (gitignored) |
| `data/pipeline/cache/` | local copies of both of the above (gitignored) |

### How stage 1 actually works

`transcribe_batch.py` is a **thin driver**; it never holds a long SSH session.

1. Factotum extracts 16 kHz mono WAV with ffmpeg into `/mnt/media6t/staging/`
   (**never** `/tmp` on the Pi — 4 GB tmpfs).
2. The WAV relays Factotum → MysteryOfGlass → MarshLair. `scp`/`rsync` cannot
   parse the space in `Blue Kitty`, and Windows `sftp` would land it on the
   near-full C:, so the bytes go over `ssh … wsl dd` straight into the WSL
   filesystem.
3. Inside WSL, `scripts/pipeline/whisper_worker.py` runs as the `systemd-run`
   unit **`posa-whisper`**, holding `large-v3` resident on the GPU across the
   whole batch (one 13–44 s load instead of one per video). The driver submits
   `job.json` and polls `result.json` with short reconnecting calls.
4. The JSON comes back and is copied to Factotum.

Both scratch WAVs reuse **one filename each** and are overwritten per video, so
nothing is ever deleted and the working set never grows.

### What a full run costs (measured, 2026-08-25)

| Stage | Rate | 112 archived videos (~200 h of audio) |
|---|---|---|
| Whisper | 17–27× realtime, model held resident | **~10 GPU-hours** |
| Judge | ~27 s per packet; a 2-hour video produces ~150 packets | **~100 GPU-hours** with `mistral-small3.2:24b` |

The judge, not the transcription, is the expensive half — the tournament
measured per-*passage* cost and the per-*video* number is the surprise here.
Two levers, in order of preference:

1. `--model qwen3.5:35b-a3b` — the tournament's understudy, near-identical
   fix rate at **35 % of the wall time** (MoE). ~35 GPU-hours for the corpus.
2. Raise the selection bar. 60–66 % of sentences currently carry a flag or a
   low-confidence word, which is far more than the tournament's hard-case
   passages implied. `LOW_CONFIDENCE_THRESHOLD` in `scripts/pipeline/flags.py`
   (0.55) and the flag filter are the two knobs.

Run the two stages **one at a time** — the GPU holds one workload at a time on
this box, and `mistral-small3.2:24b` alone is 13.9 GB of the 16 GB card.

### Polling a running batch

```bash
./venv/bin/python scripts/pipeline/transcribe_batch.py --status    # ledger view
tail -f data/pipeline/transcribe_ledger.jsonl
ssh "Blue Kitty@192.168.1.156" "wsl -d Ubuntu -u bluekitty sudo journalctl -u posa-whisper -n 20 --no-pager"
```

A crash looks exactly like "still running" unless you check: `systemctl
is-active posa-whisper` going inactive **without** a fresh `JOB_OK` is a
failure. The driver checks this itself and restarts the worker once.

### Resuming

Everything is ledger-driven and idempotent, so **just run the command again**.

* stage 1 skips any video with an `ok` ledger record *or* an existing
  `.whisper.json` on Factotum;
* stage 2 skips any video with an existing `.verdicts.json`;
* stage 3 skips any video that already has `whisper-large-v3` segments
  (`--redo` replaces them; it only ever deletes that video's Whisper rows,
  never the YouTube witnesses).

`--only VIDEO_ID` re-runs one video (note: an id starting with `-` needs
`--only=-zr_N8CDKUA`, not `--only -zr_N8CDKUA`).

### What the judge is allowed to do

* Only sentences carrying a **disagreement flag or a low-confidence Whisper
  word** are put up for judgement. Unflagged sentences are read-only context.
* A `correct` verdict with no `correction` is invalid: one repair re-ask, then
  the ruling is demoted to `escalate`.
* A correction is applied as a **minimal in-segment edit**, never a sentence
  rewrite. The applier refuses — and escalates instead — when a change:
  straddles two segments; changes nothing; rewrites more than 60 % of the
  sentence (or leaves no word standing, in a short one); **adds or drops words
  at either end of the sentence** (that is the judge dragging in the next
  utterance, not repairing this one); or lands on a segment another ruling in
  the same run has already edited. Roughly **two thirds of `correct` verdicts
  are refused this way** in practice, and that is the design working.
* Every applied edit is logged in `transcript_corrections` with the pre-edit
  text and `judge:<model>` provenance. Human approvals log
  `human:web-review`.
* A ruling on a sentence with no uncertainty signal behind it is dropped —
  the tournament measured 71 escalations of which 2 were on a genuinely hard
  span.

### Schema (migration 013)

`transcript_segments` gains `source`; `transcript_status` gains
`whisper_status` / `judge_status` / counters; plus two new tables,
`transcript_corrections` (applied-edit log) and `transcript_review_queue`
(the human queue). **The YouTube rows are never deleted** — `/search` simply
*prefers* Whisper segments for a video that has them, so a video that has not
been re-transcribed searches exactly as before.

```bash
python run_migration.py migrations/013_transcript_review.sql
```

(`apply_verdicts.py` applies it itself if the columns are missing.)

## What stays manual

- **Medium-confidence series membership.** Day Hiking and Backyard Adventures
  are proposal-only; approve them in `/admin/review/series` (Michigan
  Adventures was retired as a series 2026-08-20 — location stays a tag).
- **Multi-part trip membership.** A multi-part canoe trip with freeform titles
  will not be grouped automatically — assign it in the app or with
  `import_trips.py` / `separate_series_trips.py`.
- **Locations, weather, series notes** — curated fields, untouched by the
  updater. **Season and number of nights** are curated too, but now have
  derivation scripts behind them (`derive_seasons.py`, `derive_nights.py`) —
  high-confidence title evidence only, everything else routed to review.
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

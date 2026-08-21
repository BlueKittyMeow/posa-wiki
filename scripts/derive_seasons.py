#!/usr/bin/env python3
"""Derive ``videos.season`` from title / tag / description evidence (idempotent).

Seasons are a **video facet**, not a series. Winter is nearly binary (snow is
hard evidence); the other three are fuzzier, and **Unknown (NULL) is a
legitimate value** -- this script never guesses to fill the column.

Upload date is deliberately *not* evidence. Uploads lag filming, badly for the
early videos, so a January upload says nothing about a January shoot.

Two confidence tiers:

**High confidence** values are written straight to ``videos.season`` with
``season_confidence='high'`` and ``season_source`` recording the rule, so
provenance stays queryable::

    SELECT season, season_source, COUNT(*) FROM videos GROUP BY 1, 2;

**Medium confidence** matches are never written. They are dumped to
``data/season_review_candidates.json`` for a human pass in
``/admin/review/seasons``. Conflicts (two seasons matched) always go to
review, never auto-write -- an ambiguous video stays Unknown.

Never overwrites:

* ``season_confidence='human'`` is untouchable, full stop.
* an existing high-confidence value is only re-derived when the season is
  currently NULL (so a hand-cleared value is not silently refilled).

Idempotent: a second run writes 0 rows. Rerun it after
``scripts/update_catalog.py`` picks up new uploads.

Usage:
    python scripts/derive_seasons.py [--db path] [--dry-run] [--json path]
"""

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DB = str(REPO_ROOT / 'posa_wiki.db')
DEFAULT_JSON = str(REPO_ROOT / 'data' / 'season_review_candidates.json')

# Human decisions made in /admin/review/seasons. Videos the owner already
# ruled on are never proposed again (the queue also filters at display time,
# since this dump is regenerated wholesale on every run).
from services.review_service import (  # noqa: E402  (needs REPO_ROOT on path)
    DEFAULT_SEASON_DECISIONS_PATH, load_season_decisions)

DEFAULT_DECISIONS_JSON = str(DEFAULT_SEASON_DECISIONS_PATH)

SEASONS = ('winter', 'spring', 'summer', 'fall')

# How much of the description counts as evidence. Beyond this it is mostly
# gear links, sponsor copy and channel boilerplate -- noise, not evidence.
DESCRIPTION_WINDOW = 500

# --- high-confidence patterns ---------------------------------------------
# Winter is the strong one: hot tents, quinzees and snow are unambiguous.
RE_WINTER = re.compile(
    r'(?i)winter|hot tent|snowstorm|blizzard|quinzee|\bsnow|\bice fishing')
RE_SPRING = re.compile(r'(?i)\bspring\b')
RE_SUMMER = re.compile(r'(?i)\bsummer\b')
RE_FALL = re.compile(r'(?i)\bfall\b|\bautumn\b')

HIGH_PATTERNS = (
    ('winter', RE_WINTER),
    ('spring', RE_SPRING),
    ('summer', RE_SUMMER),
    ('fall', RE_FALL),
)

WINTER_TAG = 'winter camping'

# The 'winter camping' YouTube tag was specced as a high-confidence rule, but
# the data says otherwise: 130 videos carry it, and 37 of those share one
# *identical* 44-tag block (14 more share another, 10 another...). It is
# copy-pasted channel SEO boilerplate, not a statement about the video --
# it sits on canoe trips, the 5-year anniversary compilation, and
# "Hike and Cook - Late Start Edition". Auto-writing winter from it would
# have mislabelled ~63 videos, which is exactly the "forced guess" the
# owner's model forbids. So a tag-only match *proposes* instead of writing.
# Flip this to True to restore the original high-confidence behaviour.
TRUST_WINTER_TAG = False

# Open water contradicts ice. When a tag-only winter match lands on a title
# that is plainly a paddling trip, we do not even propose it -- Unknown is
# the honest answer and the review queue should not be padded with noise.
RE_OPEN_WATER = re.compile(r'(?i)canoe|paddl|kayak')

# --- medium-confidence patterns (review only) ------------------------------
# Holidays imply a season but not reliably: a Halloween-themed video can be
# filmed weeks early, and "Christmas Story" specials are shot in advance.
RE_FALL_HOLIDAY = re.compile(r'(?i)halloween|thanksgiving')
RE_SPRING_HOLIDAY = re.compile(r'(?i)easter|st\.? patrick')
RE_SUMMER_HOLIDAY = re.compile(r'(?i)4th of july|fourth of july')

HOLIDAY_PATTERNS = (
    ('fall', RE_FALL_HOLIDAY, 'title:holiday-fall'),
    ('spring', RE_SPRING_HOLIDAY, 'title:holiday-spring'),
    ('summer', RE_SUMMER_HOLIDAY, 'title:holiday-summer'),
)


def _tags(row):
    """Return the video's youtube_tags as a lowercase list of strings."""
    raw = row['youtube_tags'] if 'youtube_tags' in row.keys() else None
    if not raw:
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(tag).lower() for tag in parsed]


def _snippet(text, match, width=60):
    """A short window of *text* around *match*, for eyeballing in review."""
    start = max(0, match.start() - width // 2)
    end = min(len(text), match.end() + width // 2)
    prefix = '…' if start > 0 else ''
    suffix = '…' if end < len(text) else ''
    return prefix + text[start:end].strip() + suffix


def classify(row):
    """Return ``(high, review)`` for one video row.

    ``high`` is ``(season, source, evidence)`` or ``None``.
    ``review`` is a list of ``(season, rule, evidence)`` proposals.

    A video that matches two different seasons at high confidence is a
    *conflict*: nothing is written and both proposals go to review.
    """
    title = row['title'] or ''
    description = (row['description'] or '')[:DESCRIPTION_WINDOW]
    tags = _tags(row)
    review = []

    # -- title, high confidence -------------------------------------------
    title_hits = []
    for season, pattern in HIGH_PATTERNS:
        match = pattern.search(title)
        if match:
            title_hits.append((season, f'title:{season}', _snippet(title, match)))

    if len(title_hits) == 1:
        return title_hits[0], review
    if len(title_hits) > 1:
        # Conflict: "A Winter Camping Fall Special" tells us nothing certain.
        for season, source, evidence in title_hits:
            review.append((season, f'conflict:{source}', evidence))
        return None, review

    # -- tag (only when the title gave nothing) ---------------------------
    if any(WINTER_TAG in tag for tag in tags):
        if TRUST_WINTER_TAG:
            return ('winter', f'tag:{WINTER_TAG}', WINTER_TAG), review
        if not RE_OPEN_WATER.search(title):
            review.append(('winter', f'tag:{WINTER_TAG}',
                           f'youtube tag “{WINTER_TAG}” (channel boilerplate '
                           '— verify against the video)'))

    # -- medium: holidays in the title ------------------------------------
    for season, pattern, rule in HOLIDAY_PATTERNS:
        match = pattern.search(title)
        if match:
            review.append((season, rule, _snippet(title, match)))

    # -- medium: high-confidence keywords in the description --------------
    for season, pattern in HIGH_PATTERNS:
        match = pattern.search(description)
        if match:
            review.append((season, f'description:{season}',
                           _snippet(description, match)))

    # Deduplicate while keeping order (a video can hit the same season via
    # both a holiday and the description).
    seen = set()
    deduped = []
    for season, rule, evidence in review:
        if (season, rule) in seen:
            continue
        seen.add((season, rule))
        deduped.append((season, rule, evidence))
    return None, deduped


def derive(db_path=DEFAULT_DB, json_path=DEFAULT_JSON, dry_run=False,
           verbose=True, decisions_path=DEFAULT_DECISIONS_JSON):
    """Apply the high-confidence rules; dump review candidates. Returns dict."""
    decisions = load_season_decisions(decisions_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    videos = cursor.execute(
        'SELECT video_id, title, description, upload_date, youtube_tags, '
        'season, season_confidence, season_source '
        'FROM videos WHERE deleted_at IS NULL'
    ).fetchall()

    written = Counter()
    review_candidates = []
    written_total = 0
    protected_human = 0
    skipped_existing = 0
    decided_skipped = 0
    samples = []

    for row in videos:
        high, review = classify(row)

        # -- never overwrite -----------------------------------------------
        confidence = row['season_confidence']
        if confidence == 'human':
            # A person decided. Untouchable, and no point proposing again.
            protected_human += 1
            continue
        if high is not None:
            season, source, evidence = high
            if row['season'] is not None:
                # An existing value is only re-derived when currently NULL.
                skipped_existing += 1
            else:
                cursor.execute(
                    'UPDATE videos SET season = ?, season_confidence = ?, '
                    'season_source = ?, updated_at = ? WHERE video_id = ?',
                    (season, 'high', source,
                     datetime.now().isoformat(), row['video_id']),
                )
                if cursor.rowcount:
                    written[season] += 1
                    written_total += 1
                    samples.append({'video_id': row['video_id'],
                                    'title': row['title'],
                                    'season': season, 'source': source,
                                    'evidence': evidence})
            continue

        # -- medium confidence: propose only -------------------------------
        for season, rule, evidence in review:
            if row['video_id'] in decisions:
                decided_skipped += 1
                continue
            review_candidates.append({
                'video_id': row['video_id'],
                'title': row['title'],
                'upload_date': row['upload_date'],
                'proposed_season': season,
                'rule': rule,
                'evidence': evidence,
                'confidence': 'medium',
            })

    if dry_run:
        conn.rollback()
    else:
        conn.commit()

    # Post-run totals across the whole catalogue.
    totals = {}
    for season in SEASONS:
        totals[season] = cursor.execute(
            'SELECT COUNT(*) FROM videos WHERE season = ? '
            'AND deleted_at IS NULL', (season,)).fetchone()[0]
    unknown = cursor.execute(
        'SELECT COUNT(*) FROM videos WHERE season IS NULL '
        'AND deleted_at IS NULL').fetchone()[0]
    conn.close()

    payload = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'database': db_path,
        'count': len(review_candidates),
        'note': 'Medium-confidence season proposals only. Nothing here has '
                'been written to the database; a human decides (see '
                '/admin/review/seasons). Unknown is a legitimate answer -- '
                'reject anything that is not actually evident.',
        'already_decided_skipped': decided_skipped,
        'candidates': review_candidates,
    }
    if not dry_run and json_path:
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_path).write_text(json.dumps(payload, indent=2) + '\n')

    if verbose:
        print(f'🍂 derive_seasons over {len(videos)} videos in {db_path}'
              + ('  (dry run)' if dry_run else ''))
        print(f'\n   Written this run: {written_total}')
        for season in SEASONS:
            if written[season]:
                print(f'      + {season:8s} {written[season]}')

        print('\n   Season totals (whole catalogue):')
        for season in SEASONS:
            print(f'      {season:8s} {totals[season]}')
        print(f'      {"unknown":8s} {unknown}')

        by_season = Counter(c['proposed_season'] for c in review_candidates)
        print(f'\n   Review candidates: {len(review_candidates)}'
              + ('' if dry_run else f' -> {json_path}'))
        for season, count in sorted(by_season.items()):
            print(f'      ? {season:8s} {count}')

        if protected_human:
            print(f'\n   Protected (human decisions): {protected_human}')
        if skipped_existing:
            print(f'   Left alone (already had a season): {skipped_existing}')
        if decided_skipped:
            print(f'   Skipped (already decided in /admin): {decided_skipped}')

        if samples:
            print('\n   Sample assignments:')
            for sample in samples[:10]:
                print(f'      {sample["season"]:7s} ← {sample["title"][:58]}'
                      f'   [{sample["source"]}]')

    return {
        'videos_scanned': len(videos),
        'written_total': written_total,
        'written_by_season': dict(written),
        'totals_by_season': totals,
        'unknown': unknown,
        'review_candidates': len(review_candidates),
        'review_by_season': dict(Counter(
            c['proposed_season'] for c in review_candidates)),
        'protected_human': protected_human,
        'skipped_existing': skipped_existing,
        'already_decided_skipped': decided_skipped,
        'samples': samples,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=DEFAULT_DB, help='database path')
    parser.add_argument('--json', default=DEFAULT_JSON,
                        help='review-candidate output path')
    parser.add_argument('--dry-run', action='store_true',
                        help='roll back and skip the JSON dump')
    parser.add_argument('--decisions', default=DEFAULT_DECISIONS_JSON,
                        help='human review decisions to skip')
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args()

    derive(args.db, args.json, dry_run=args.dry_run, verbose=not args.quiet,
           decisions_path=args.decisions)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

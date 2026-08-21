#!/usr/bin/env python3
"""Auto-populate ``video_series`` from title / tag patterns (idempotent).

Two confidence tiers:

**High confidence** rows are inserted straight into ``video_series`` with a
``notes`` value recording *why* (``auto:title-pattern``, ``auto:tag-match``,
``auto:episode-pattern``, ``auto:implied-by-child``), so provenance stays
queryable::

    SELECT notes, COUNT(*) FROM video_series GROUP BY notes;

**Medium confidence** matches are never written to the database.  They are
dumped to ``data/series_review_candidates.json`` for a human pass.

Membership in a Community Content child (Unboxing / Channel Updates /
Giveaways) always implies membership in the Community Content umbrella; the
script writes both rows.

Idempotent: rows use ``INSERT OR IGNORE`` against the
``(video_id, series_id)`` primary key, so a second run inserts 0.  Rerun it
after ``scripts/update_catalog.py`` picks up new uploads.

Usage:
    python scripts/assign_series.py [--db path] [--dry-run] [--json path]
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
DEFAULT_JSON = str(REPO_ROOT / 'data' / 'series_review_candidates.json')

COMMUNITY_UMBRELLA = 'Community Content'
COMMUNITY_CHILDREN = ('Unboxing', 'Channel Updates', 'Giveaways')

# --- high-confidence title patterns ---------------------------------------
RE_WINTER = re.compile(r'(?i)winter|hot tent|snowstorm|\bsnow')
RE_CANOE = re.compile(r'(?i)canoe|paddl')
RE_FISHING_SHOW = re.compile(r'(?i)unsuccessful fishing show')
RE_FISHING_EPISODE = re.compile(r'(?i)episode\s+(\d+)')
RE_CHRISTMAS_STORY = re.compile(r'(?i)christmas story')
RE_CHRISTMAS_NUMBER = re.compile(r'(?i)christmas story\s*(\d+)')
RE_UNBOXING = re.compile(r'(?i)unbox')
RE_UPDATE = re.compile(r'(?i)\bupdate')
RE_GIVEAWAY = re.compile(r'(?i)giveaway|give away')
RE_BOUNDARY_WATERS = re.compile(r'(?i)boundary waters|bwca')
RE_ISLE_ROYALE = re.compile(r'(?i)isle royale')
RE_SPECIAL_OCCASION = re.compile(
    r'(?i)birthday|christmas|thanksgiving|easter|st\.? patrick|'
    r'4th of july|halloween|valentine|new year'
)
HIKE_AND_COOK_PREFIX = 'hike and cook'

# --- medium-confidence patterns (review only) ------------------------------
RE_HIKE = re.compile(r'(?i)\bhike|hiking')
RE_OVERNIGHT = re.compile(r'(?i)overnight|night|camp')
RE_BACKYARD = re.compile(r'(?i)backyard')


def _tags(row):
    """Return the video's youtube_tags as a lowercase list of strings."""
    raw = row['youtube_tags']
    if not raw:
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(tag).lower() for tag in parsed]


def _tag_hit(tags, needle):
    return any(needle in tag for tag in tags)


def _tag_re_hit(tags, pattern):
    return any(pattern.search(tag) for tag in tags)


def classify(row):
    """Return (high_confidence, review) for one video row.

    ``high_confidence`` is a list of ``(series_name, episode_number, notes)``.
    ``review`` is a list of ``(series_name, rule)``.
    """
    title = row['title'] or ''
    description = row['description'] or ''
    tags = _tags(row)
    high = []
    review = []

    def add(series_name, note, episode=None):
        if series_name not in {s for s, _, _ in high}:
            high.append((series_name, episode, note))

    # -- Winter Camping ----------------------------------------------------
    if RE_WINTER.search(title):
        add('Winter Camping', 'auto:title-pattern')
    elif _tag_hit(tags, 'winter camping'):
        add('Winter Camping', 'auto:tag-match')

    # -- Canoe Camping -----------------------------------------------------
    if RE_CANOE.search(title):
        add('Canoe Camping', 'auto:title-pattern')
    elif _tag_hit(tags, 'canoe'):
        add('Canoe Camping', 'auto:tag-match')

    # -- Unsuccessful Fishing Show (episodic, numbered) --------------------
    if RE_FISHING_SHOW.search(title):
        match = RE_FISHING_EPISODE.search(title)
        episode = int(match.group(1)) if match else None
        add('Unsuccessful Fishing Show', 'auto:episode-pattern', episode)

    # -- Hike and Cook (episodic by upload date; also a day hike) ----------
    if title.lower().startswith(HIKE_AND_COOK_PREFIX):
        add('Hike and Cook', 'auto:title-pattern')
        add('Day Hiking', 'auto:title-pattern')
    elif HIKE_AND_COOK_PREFIX in title.lower():
        # e.g. "Halloween Hike and Cook" -- almost certainly the show, but
        # the prefix rule is the high-confidence one, so flag for review.
        review.append(('Hike and Cook', 'title-contains-hike-and-cook'))

    # -- A Winter Camping Christmas Story (episodic, numbered 1-6) ---------
    if RE_CHRISTMAS_STORY.search(title):
        match = RE_CHRISTMAS_NUMBER.search(title)
        # The first special (2017) carries no number in its title.
        episode = int(match.group(1)) if match else 1
        add('A Winter Camping Christmas Story', 'auto:episode-pattern',
            episode)

    # -- Community Content children ---------------------------------------
    if RE_UNBOXING.search(title):
        add('Unboxing', 'auto:title-pattern')
    if RE_UPDATE.search(title):
        add('Channel Updates', 'auto:title-pattern')
    if RE_GIVEAWAY.search(title):
        add('Giveaways', 'auto:title-pattern')
    elif _tag_re_hit(tags, RE_GIVEAWAY):
        add('Giveaways', 'auto:tag-match')

    # Membership in any child implies the umbrella.
    if any(name in COMMUNITY_CHILDREN for name, _, _ in high):
        add(COMMUNITY_UMBRELLA, 'auto:implied-by-child')

    # -- Locations ---------------------------------------------------------
    if RE_BOUNDARY_WATERS.search(title):
        add('Boundary Waters', 'auto:title-pattern')
    elif _tag_re_hit(tags, RE_BOUNDARY_WATERS):
        add('Boundary Waters', 'auto:tag-match')

    if RE_ISLE_ROYALE.search(title):
        add('Isle Royale', 'auto:title-pattern')

    # -- Special Occasions -------------------------------------------------
    if RE_SPECIAL_OCCASION.search(title):
        add('Special Occasions', 'auto:title-pattern')

    # -- medium confidence: Day Hiking ------------------------------------
    already_day_hiking = any(name == 'Day Hiking' for name, _, _ in high)
    if (not already_day_hiking and RE_HIKE.search(title)
            and not RE_OVERNIGHT.search(title)):
        review.append(('Day Hiking', 'title-hike-without-overnight'))

    # -- medium confidence: Backyard Adventures ---------------------------
    if (RE_BACKYARD.search(title) or RE_BACKYARD.search(description)
            or _tag_re_hit(tags, RE_BACKYARD)):
        review.append(('Backyard Adventures', 'backyard-in-title-desc-tags'))

    # Michigan Adventures was retired as a series (owner decision 2026-08-20):
    # location-in-Michigan stays a tag-level fact, not a collection. No rule.

    return high, review


def assign(db_path=DEFAULT_DB, json_path=DEFAULT_JSON, dry_run=False,
           verbose=True):
    """Apply the high-confidence rules; dump review candidates. Returns dict."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    series_ids = {
        row['name']: row['series_id']
        for row in cursor.execute('SELECT series_id, name FROM series')
    }

    videos = cursor.execute(
        'SELECT video_id, title, description, upload_date, youtube_tags '
        'FROM videos WHERE deleted_at IS NULL'
    ).fetchall()

    inserted_counts = Counter()
    missing_series = Counter()
    review_candidates = []
    inserted_total = 0

    for row in videos:
        high, review = classify(row)

        for series_name, episode_number, notes in high:
            series_id = series_ids.get(series_name)
            if series_id is None:
                missing_series[series_name] += 1
                continue
            cursor.execute(
                'INSERT OR IGNORE INTO video_series '
                '(video_id, series_id, episode_number, trip_id, notes) '
                'VALUES (?, ?, ?, NULL, ?)',
                (row['video_id'], series_id, episode_number, notes),
            )
            if cursor.rowcount:
                inserted_counts[series_name] += 1
                inserted_total += 1

        for series_name, rule in review:
            review_candidates.append({
                'video_id': row['video_id'],
                'title': row['title'],
                'upload_date': row['upload_date'],
                'proposed_series': series_name,
                'rule': rule,
                'confidence': 'medium',
            })

    # Per-series membership totals (after this run).
    totals = {}
    if not dry_run:
        conn.commit()
    for name, series_id in sorted(series_ids.items()):
        totals[name] = cursor.execute(
            'SELECT COUNT(*) FROM video_series WHERE series_id = ?',
            (series_id,),
        ).fetchone()[0]

    if dry_run:
        conn.rollback()
    conn.close()

    payload = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'database': db_path,
        'count': len(review_candidates),
        'note': 'Medium-confidence proposals only. Nothing here has been '
                'written to the database; a human decides.',
        'candidates': review_candidates,
    }
    if not dry_run and json_path:
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_path).write_text(json.dumps(payload, indent=2) + '\n')

    if verbose:
        print(f'🏷️  assign_series over {len(videos)} videos in {db_path}')
        print(f'\n   Inserted this run: {inserted_total}')
        for name, count in sorted(inserted_counts.items()):
            print(f'      + {name:34s} {count}')
        if missing_series:
            print('\n   ⚠️  series rows missing (run seed_series.py first):')
            for name, count in missing_series.items():
                print(f'      ! {name:34s} {count} video(s) skipped')
        print('\n   Membership totals by series:')
        for name, count in sorted(totals.items(), key=lambda kv: -kv[1]):
            print(f'      {name:34s} {count}')
        by_rule = Counter(c['proposed_series'] for c in review_candidates)
        print(f'\n   Review candidates: {len(review_candidates)}'
              + ('' if dry_run else f' -> {json_path}'))
        for name, count in sorted(by_rule.items()):
            print(f'      ? {name:34s} {count}')

    return {
        'videos_scanned': len(videos),
        'inserted_total': inserted_total,
        'inserted_by_series': dict(inserted_counts),
        'totals_by_series': totals,
        'review_candidates': len(review_candidates),
        'review_by_series': dict(Counter(
            c['proposed_series'] for c in review_candidates)),
        'missing_series': dict(missing_series),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=DEFAULT_DB, help='database path')
    parser.add_argument('--json', default=DEFAULT_JSON,
                        help='review-candidate output path')
    parser.add_argument('--dry-run', action='store_true',
                        help='roll back and skip the JSON dump')
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args()

    assign(args.db, args.json, dry_run=args.dry_run, verbose=not args.quiet)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

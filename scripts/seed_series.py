#!/usr/bin/env python3
"""Seed the canonical ``series`` taxonomy (idempotent).

The ``series`` table is the source of truth for *thematic* groupings of
videos; ``trips`` is reserved for genuine multi-part trips (one adventure
split across several uploads).  This script brings the ``series`` table in
line with the owner-approved taxonomy (2026-08-20, see
``docs/research/SERIES_REDESIGN.md``):

  * upserts every canonical series row, matched **by name** (never by id --
    the production database's ids may differ from the local copy)
  * retires the "Spring Camping" / "Fall Camping" rows (seasons become a
    facet later, not a series); refuses to touch them if anything actually
    references them
  * migrates "The Unsuccessful Fishing Show" out of ``trips`` /
    ``video_versions`` and into ``series`` / ``video_series``, carrying the
    episode numbers across, then removes the now-empty trip

Safe to run repeatedly: a second run reports 0 changes.

Usage:
    python scripts/seed_series.py [--db path/to/posa_wiki.db] [--dry-run]
"""

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DB = str(REPO_ROOT / 'posa_wiki.db')

# The canonical taxonomy: (name, description, is_episodic, series_type).
# ``series_type`` drives the grouping headers on /series.
CANONICAL_SERIES = [
    # --- activity -------------------------------------------------------
    ('Winter Camping', 'Cold weather camping adventures', 0, 'activity'),
    ('Canoe Camping', 'Paddling and canoe-based adventures', 0, 'activity'),
    ('Backpacking', 'Multi-day hiking adventures', 0, 'activity'),
    ('Day Hiking', 'Single-day outdoor adventures, no overnight', 0,
     'activity'),
    # --- location -------------------------------------------------------
    ('Boundary Waters', 'Boundary Waters Canoe Area adventures', 0,
     'location'),
    ('Isle Royale', 'Isle Royale National Park adventures', 0, 'location'),
    ('Michigan Adventures', 'Michigan-based outdoor content', 0, 'location'),
    ('Backyard Adventures', 'Home-based adventures in and around the yard',
     0, 'location'),
    # --- content --------------------------------------------------------
    ('Community Content',
     'Umbrella series: giveaways, unboxings and channel updates', 0,
     'content'),
    ('Unboxing', 'Fan mail and gear unboxings', 0, 'content'),
    ('Channel Updates', 'Channel news, milestones and updates', 0, 'content'),
    ('Giveaways', 'Subscriber giveaways and their results', 0, 'content'),
    ('Unsuccessful Fishing Show', 'Episodic fishing adventure series', 1,
     'content'),
    ('Hike and Cook',
     'The Hike and Cook show -- day hikes with a campfire meal '
     '(episodic by upload date, not by number)', 1, 'content'),
    ('A Winter Camping Christmas Story',
     'The annual Christmas Eve/Day winter camping special (numbered 1-6)',
     1, 'content'),
    # --- special --------------------------------------------------------
    ('Special Occasions', 'Birthdays, holidays, and celebrations', 0,
     'special'),
]

# Children of the "Community Content" umbrella.  Membership in a child
# implies membership in the umbrella (enforced by assign_series.py).
COMMUNITY_CHILDREN = ('Unboxing', 'Channel Updates', 'Giveaways')

# Seasons are being retired as series -- they become a facet of the video
# record later.  Removing the rows keeps /series honest; the script is the
# documentation of the decision.
RETIRED_SERIES = ('Spring Camping', 'Fall Camping')

# The trip row that was really a thematic show all along.
FISHING_TRIP_NAME = 'The Unsuccessful Fishing Show'
FISHING_SERIES_NAME = 'Unsuccessful Fishing Show'


def upsert_series(cursor, verbose=True):
    """Insert missing canonical series, update drifted metadata.

    Matching is by ``name`` so the same script works against databases with
    different id sequences (local vs production).
    """
    inserted = updated = 0

    for name, description, is_episodic, series_type in CANONICAL_SERIES:
        row = cursor.execute(
            'SELECT series_id, description, is_episodic, series_type '
            'FROM series WHERE name = ?', (name,),
        ).fetchone()

        if row is None:
            cursor.execute(
                'INSERT INTO series (name, description, is_episodic, '
                'series_type) VALUES (?, ?, ?, ?)',
                (name, description, is_episodic, series_type),
            )
            inserted += 1
            if verbose:
                print(f'   ➕ series: {name} ({series_type})')
            continue

        current = (row[1], int(row[2] or 0), row[3])
        wanted = (description, is_episodic, series_type)
        if current != wanted:
            cursor.execute(
                'UPDATE series SET description = ?, is_episodic = ?, '
                'series_type = ? WHERE series_id = ?',
                (description, is_episodic, series_type, row[0]),
            )
            updated += 1
            if verbose:
                print(f'   ✏️  series updated: {name}')

    return inserted, updated


def retire_series(cursor, verbose=True):
    """Remove the retired season series, unless something references them."""
    removed = skipped = 0

    for name in RETIRED_SERIES:
        row = cursor.execute(
            'SELECT series_id FROM series WHERE name = ?', (name,),
        ).fetchone()
        if row is None:
            continue

        series_id = row[0]
        refs = cursor.execute(
            'SELECT COUNT(*) FROM video_series WHERE series_id = ?',
            (series_id,),
        ).fetchone()[0]
        if refs:
            skipped += 1
            if verbose:
                print(f'   ⚠️  {name} still has {refs} membership(s) — '
                      f'left in place, resolve by hand')
            continue

        cursor.execute('DELETE FROM series WHERE series_id = ?', (series_id,))
        removed += 1
        if verbose:
            print(f'   🗂️  retired series: {name} (seasons become a facet)')

    return removed, skipped


def migrate_fishing_show(cursor, verbose=True):
    """Move the Fishing Show from trips/video_versions to video_series.

    Episode numbers ride along in ``video_series.episode_number``.  Once the
    episodes are safely migrated the trip row and its ``video_versions`` rows
    are removed -- the Fishing Show is a show, not a trip.
    """
    result = {'migrated': 0, 'trip_removed': 0, 'versions_removed': 0}

    trip = cursor.execute(
        'SELECT trip_id FROM trips WHERE trip_name = ?',
        (FISHING_TRIP_NAME,),
    ).fetchone()
    if trip is None:
        if verbose:
            print('   ✓ Fishing Show trip already migrated (nothing to do)')
        return result
    trip_id = trip[0]

    series = cursor.execute(
        'SELECT series_id FROM series WHERE name = ?', (FISHING_SERIES_NAME,),
    ).fetchone()
    if series is None:
        raise RuntimeError(
            f'series {FISHING_SERIES_NAME!r} missing — run upsert first'
        )
    series_id = series[0]

    episodes = cursor.execute(
        'SELECT video_id, part_number FROM video_versions WHERE trip_id = ?',
        (trip_id,),
    ).fetchall()

    for video_id, part_number in episodes:
        cursor.execute(
            'INSERT OR IGNORE INTO video_series '
            '(video_id, series_id, episode_number, trip_id, notes) '
            'VALUES (?, ?, ?, NULL, ?)',
            (video_id, series_id, part_number, 'migrated:trip-episode'),
        )
        if cursor.rowcount:
            result['migrated'] += 1
        else:
            # Row already there (rerun, or assign_series ran first) -- make
            # sure the episode number from the trip is preserved.
            cursor.execute(
                'UPDATE video_series SET episode_number = ? '
                'WHERE video_id = ? AND series_id = ? '
                'AND episode_number IS NULL',
                (part_number, video_id, series_id),
            )

    cursor.execute('DELETE FROM video_versions WHERE trip_id = ?', (trip_id,))
    result['versions_removed'] = cursor.rowcount

    cursor.execute('DELETE FROM trips WHERE trip_id = ?', (trip_id,))
    result['trip_removed'] = cursor.rowcount

    if verbose:
        print(f'   🎣 Fishing Show: {result["migrated"]} episode(s) migrated '
              f'to video_series, {result["versions_removed"]} video_versions '
              f'row(s) and {result["trip_removed"]} trip row removed')

    return result


def seed(db_path=DEFAULT_DB, dry_run=False, verbose=True):
    """Run the whole seed. Returns a summary dict."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        if verbose:
            print(f'📚 Seeding series taxonomy in {db_path}')

        inserted, updated = upsert_series(cursor, verbose)
        removed, skipped = retire_series(cursor, verbose)
        fishing = migrate_fishing_show(cursor, verbose)

        if dry_run:
            conn.rollback()
            if verbose:
                print('   (dry run — rolled back)')
        else:
            conn.commit()
    finally:
        conn.close()

    summary = {
        'series_inserted': inserted,
        'series_updated': updated,
        'series_retired': removed,
        'series_retire_skipped': skipped,
        'fishing_episodes_migrated': fishing['migrated'],
        'fishing_versions_removed': fishing['versions_removed'],
        'fishing_trip_removed': fishing['trip_removed'],
    }

    if verbose:
        print('\n📊 Summary')
        for key, value in summary.items():
            print(f'   {key:28s} {value}')

    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=DEFAULT_DB, help='database path')
    parser.add_argument('--dry-run', action='store_true',
                        help='roll back instead of committing')
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args()

    seed(args.db, dry_run=args.dry_run, verbose=not args.quiet)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

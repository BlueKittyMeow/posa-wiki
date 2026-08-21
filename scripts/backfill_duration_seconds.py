#!/usr/bin/env python3
"""Backfill videos.duration_seconds from the human-readable videos.duration.

Run after applying migrations/008_add_duration_seconds.sql:

    python scripts/backfill_duration_seconds.py [--db posa_wiki.db] [--all] [--dry-run]

By default only rows where duration_seconds IS NULL are touched; --all
recomputes every row.
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.duration import parse_duration_to_seconds  # noqa: E402

DEFAULT_DB = os.getenv('DATABASE_PATH') or str(
    Path(__file__).resolve().parent.parent / 'posa_wiki.db'
)


def backfill(db_path, recompute_all=False, dry_run=False):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        columns = {row['name'] for row in conn.execute('PRAGMA table_info(videos)')}
        if 'duration_seconds' not in columns:
            print('Error: videos.duration_seconds is missing. '
                  'Run migrations/008_add_duration_seconds.sql first.', file=sys.stderr)
            return 1

        sql = 'SELECT video_id, duration, duration_seconds FROM videos'
        if not recompute_all:
            sql += ' WHERE duration_seconds IS NULL'
        rows = conn.execute(sql).fetchall()

        updates = []
        unparseable = []
        empty = 0
        for row in rows:
            if row['duration'] is None or str(row['duration']).strip() == '':
                empty += 1
                continue
            seconds = parse_duration_to_seconds(row['duration'])
            if seconds is None:
                unparseable.append((row['video_id'], row['duration']))
                continue
            if seconds != row['duration_seconds']:
                updates.append((seconds, row['video_id']))

        print(f'Candidate rows:   {len(rows)}')
        print(f'  to update:      {len(updates)}')
        print(f'  blank duration: {empty}')
        print(f'  unparseable:    {len(unparseable)}')
        for video_id, raw in unparseable[:20]:
            print(f'    {video_id}: {raw!r}')

        if dry_run:
            print('Dry run - no changes written.')
            return 0

        conn.executemany(
            'UPDATE videos SET duration_seconds = ? WHERE video_id = ?', updates
        )
        conn.commit()

        remaining = conn.execute(
            'SELECT COUNT(*) FROM videos WHERE duration_seconds IS NULL'
        ).fetchone()[0]
        print(f'Done. Rows still NULL: {remaining}')
        return 0
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=DEFAULT_DB, help='Path to posa_wiki.db')
    parser.add_argument('--all', action='store_true', dest='recompute_all',
                        help='Recompute every row, not just NULLs')
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would change without writing')
    args = parser.parse_args()
    return backfill(args.db, args.recompute_all, args.dry_run)


if __name__ == '__main__':
    sys.exit(main())

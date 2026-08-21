#!/usr/bin/env python3
"""Incremental "keep current" updater for the Posa wiki catalog.

Fetches new uploads from the YouTube Data API v3 (uploads-playlist method --
never the Search API, see ``docs/research/API_SCRAPING_LESSONS.md``), inserts
any videos the database has not seen yet, and runs the downstream enrichment
that used to be a pile of one-off scripts:

  * duration / duration_seconds + youtube_tags validated/unvalidated split
  * description mining -> video_people / video_dogs junction rows
  * episode auto-assignment for recognised episodic series (see ``PATTERNS``)

Designed to run headless (cron / systemd timer) or by hand.  It is idempotent:
running it twice in a row inserts nothing the second time.  New rows are
INSERTed, never REPLACEd, so curated columns are never clobbered.

Usage:
    python scripts/update_catalog.py --dry-run
    YOUTUBE_API_KEY=... python scripts/update_catalog.py
    YOUTUBE_API_KEY=... python scripts/update_catalog.py --refresh-stats
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.duration import parse_duration_to_seconds  # noqa: E402
from import_missing_videos import (  # noqa: E402
    load_tag_authorities,
    parse_duration,
    validate_tags,
)
from mine_video_descriptions import (  # noqa: E402
    analyze_description,
    load_known_entities,
)
from populate_people_dogs import (  # noqa: E402
    DOGS_MAPPING,
    ensure_family_members,
    link_entities,
)

API_BASE = 'https://www.googleapis.com/youtube/v3'
CHANNEL_HANDLE = 'MatthewPosa'
PAGE_SIZE = 50
API_SLEEP = 0.3  # polite pause between API calls
DEFAULT_DB = str(REPO_ROOT / 'posa_wiki.db')
TAG_AUTHORITY_PATH = str(REPO_ROOT / 'tag_authority_system.json')

# Episodic series auto-assignment.  Add a new series in one line: a title
# regex, the trip_name it belongs to, and how to pull the episode number out.
PATTERNS = [
    {
        'trip_name': 'The Unsuccessful Fishing Show',
        'title_re': re.compile(r'unsuccessful fishing show', re.IGNORECASE),
        'episode_re': re.compile(r'episode\s+(\d+)', re.IGNORECASE),
        'version_type': 'episode',
    },
]


# ---------------------------------------------------------------------------
# API key
# ---------------------------------------------------------------------------

def get_api_key(api_md_path=None):
    """Return the YouTube API key from ``$YOUTUBE_API_KEY`` or ``api.md``.

    Raises ``RuntimeError`` with a clear message when neither is available.
    The key itself is never printed.
    """
    key = os.environ.get('YOUTUBE_API_KEY', '').strip()
    if key:
        return key

    path = Path(api_md_path) if api_md_path else (REPO_ROOT / 'api.md')
    if path.exists():
        key = path.read_text().strip()
        if key:
            return key

    raise RuntimeError(
        'No YouTube API key found. Set the YOUTUBE_API_KEY environment '
        f'variable, or create {path} containing the key (gitignored).'
    )


# ---------------------------------------------------------------------------
# API access (these three fetch_* functions are what tests monkeypatch)
# ---------------------------------------------------------------------------

def api_get(endpoint, params, api_key, _retried=False):
    """GET an API endpoint with one polite retry on 5xx / rate-limit errors."""
    import requests  # imported lazily so --dry-run/tests need no network stack

    query = dict(params)
    query['key'] = api_key
    response = requests.get(f'{API_BASE}/{endpoint}', params=query, timeout=30)
    time.sleep(API_SLEEP)

    if response.status_code == 200:
        return response.json()

    retryable = response.status_code >= 500 or response.status_code in (403, 429)
    if retryable and not _retried:
        print(f'   ⚠️  API {response.status_code} on {endpoint}; retrying in 5s...')
        time.sleep(5)
        return api_get(endpoint, params, api_key, _retried=True)

    raise RuntimeError(
        f'YouTube API error {response.status_code} on {endpoint}: '
        f'{response.text[:300]}'
    )


def fetch_uploads_playlist_id(api_key, handle=CHANNEL_HANDLE):
    """Resolve the channel handle to its uploads playlist id (UC -> UU)."""
    data = api_get('channels', {'part': 'id', 'forHandle': handle}, api_key)
    items = data.get('items') or []
    if not items:
        raise RuntimeError(f'Channel @{handle} not found')
    channel_id = items[0]['id']
    return channel_id.replace('UC', 'UU', 1)


def fetch_playlist_page(api_key, playlist_id, page_token=None):
    """Return ``(video_ids, next_page_token)`` for one uploads-playlist page."""
    params = {
        'part': 'contentDetails',
        'playlistId': playlist_id,
        'maxResults': PAGE_SIZE,
    }
    if page_token:
        params['pageToken'] = page_token

    data = api_get('playlistItems', params, api_key)
    ids = [
        item['contentDetails']['videoId']
        for item in data.get('items', [])
        if item.get('contentDetails', {}).get('videoId')
    ]
    return ids, data.get('nextPageToken')


def fetch_video_details(api_key, video_ids):
    """Batch-fetch full metadata for up to 50 video ids."""
    if not video_ids:
        return []
    data = api_get(
        'videos',
        {
            'part': 'id,snippet,contentDetails,statistics',
            'id': ','.join(video_ids),
        },
        api_key,
    )
    return data.get('items', [])


# ---------------------------------------------------------------------------
# Delta discovery
# ---------------------------------------------------------------------------

def discover_new_video_ids(api_key, playlist_id, existing_ids, full_scan=False,
                           verbose=True):
    """Walk the uploads playlist newest-first, collecting unknown video ids.

    Stops as soon as a full page contains only ids already in the DB, unless
    ``full_scan`` is set (then every page is walked).  Also returns every id
    seen, which ``--refresh-stats`` uses.
    """
    new_ids = []
    seen_ids = []
    page_token = None
    page = 0

    while True:
        page += 1
        ids, page_token = fetch_playlist_page(api_key, playlist_id, page_token)
        if not ids:
            break

        seen_ids.extend(ids)
        unknown = [vid for vid in ids if vid not in existing_ids and vid not in new_ids]
        new_ids.extend(unknown)

        if verbose:
            print(f'   Page {page}: {len(ids)} ids, {len(unknown)} new')

        if not full_scan and not unknown:
            if verbose:
                print('   Page contained only known videos — stopping delta walk.')
            break
        if not page_token:
            break

    return new_ids, seen_ids


# ---------------------------------------------------------------------------
# Insert / update
# ---------------------------------------------------------------------------

def build_row(video, alias_to_authority):
    """Map a YouTube API video item onto the ``videos`` column set."""
    snippet = video.get('snippet', {})
    statistics = video.get('statistics', {})
    content_details = video.get('contentDetails', {})

    raw_duration = content_details.get('duration')
    published = snippet.get('publishedAt') or ''
    original_tags = snippet.get('tags', []) or []
    validated_tags, unvalidated_tags = validate_tags(original_tags, alias_to_authority)

    return {
        'video_id': video['id'],
        'title': snippet.get('title', ''),
        'upload_date': published[:10] if published else None,
        'duration': parse_duration(raw_duration),
        'duration_seconds': parse_duration_to_seconds(raw_duration),
        'view_count': int(statistics.get('viewCount') or 0),
        'like_count': int(statistics.get('likeCount') or 0),
        'description': snippet.get('description', ''),
        'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
        'youtube_tags': original_tags,
        'validated_tags': validated_tags,
        'unvalidated_tags': unvalidated_tags,
    }


def insert_video(cursor, row):
    """INSERT a new videos row (never REPLACE — curated columns are sacred)."""
    now = datetime.now().isoformat()
    cursor.execute('''
    INSERT INTO videos (
        video_id, title, upload_date, duration, duration_seconds, view_count,
        like_count, description, thumbnail_url, youtube_tags, validated_tags,
        unvalidated_tags, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        row['video_id'], row['title'], row['upload_date'], row['duration'],
        row['duration_seconds'], row['view_count'], row['like_count'],
        row['description'], row['thumbnail_url'],
        json.dumps(row['youtube_tags']), json.dumps(row['validated_tags']),
        json.dumps(row['unvalidated_tags']), now, now,
    ))


def refresh_stats(cursor, row):
    """Update only the volatile counters for an existing video."""
    cursor.execute('''
    UPDATE videos
       SET view_count = ?, like_count = ?, updated_at = ?
     WHERE video_id = ?
    ''', (row['view_count'], row['like_count'], datetime.now().isoformat(),
          row['video_id']))
    return cursor.rowcount


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------

def enrich_people_dogs(cursor, rows, verbose=True):
    """Mine descriptions for new rows and add junction links."""
    known_people, known_dogs, family_terms, common_names = load_known_entities()
    people_mapping = ensure_family_members(cursor, verbose=verbose)
    dogs_mapping = dict(DOGS_MAPPING)

    people_added = 0
    dogs_added = 0

    for row in rows:
        high, _medium, _low = analyze_description(
            row['description'], known_people, known_dogs, family_terms, common_names
        )
        if not high:
            continue
        added_p, added_d = link_entities(
            cursor, row['video_id'], high, people_mapping, dogs_mapping,
            verbose=verbose,
        )
        people_added += added_p
        dogs_added += added_d

    return people_added, dogs_added


def assign_episodes(cursor, rows, verbose=True):
    """Auto-assign episodic videos to their trip via ``video_versions``."""
    assigned = 0

    for row in rows:
        title = row['title'] or ''
        for pattern in PATTERNS:
            if not pattern['title_re'].search(title):
                continue
            match = pattern['episode_re'].search(title)
            if not match:
                continue

            trip = cursor.execute(
                'SELECT trip_id FROM trips WHERE trip_name = ?',
                (pattern['trip_name'],),
            ).fetchone()
            if not trip:
                if verbose:
                    print(f"   ⚠️  Trip '{pattern['trip_name']}' not found — "
                          f'skipping episode assignment for {row["video_id"]}')
                break
            trip_id = trip[0]

            already = cursor.execute(
                'SELECT 1 FROM video_versions WHERE trip_id = ? AND video_id = ?',
                (trip_id, row['video_id']),
            ).fetchone()
            if already:
                break

            episode_num = int(match.group(1))
            cursor.execute('''
            INSERT INTO video_versions (trip_id, version_type, part_number,
                                        total_parts, video_id)
            VALUES (?, ?, ?, ?, ?)
            ''', (trip_id, pattern['version_type'], episode_num, None,
                  row['video_id']))
            assigned += 1
            if verbose:
                print(f'   🎬 {row["video_id"]}: '
                      f'{pattern["trip_name"]} episode {episode_num}')

            # Keep total_parts consistent across the trip.
            total = cursor.execute(
                'SELECT COUNT(*) FROM video_versions WHERE trip_id = ?',
                (trip_id,),
            ).fetchone()[0]
            cursor.execute(
                'UPDATE video_versions SET total_parts = ? WHERE trip_id = ?',
                (total, trip_id),
            )
            break

    return assigned


def check_fts_triggers(cursor):
    """Warn (do not rebuild) if the videos FTS sync triggers are missing."""
    names = {
        row[0] for row in cursor.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' "
            "AND name IN ('videos_ai', 'videos_au', 'videos_ad')"
        ).fetchall()
    }
    missing = {'videos_ai', 'videos_au', 'videos_ad'} - names
    if missing:
        print(f'⚠️  FTS triggers missing: {", ".join(sorted(missing))}. '
              'New rows will NOT be searchable — run build_fts_index.py.')
        return False
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def update_catalog(db_path=DEFAULT_DB, api_key=None, dry_run=False,
                   full_scan=False, do_refresh_stats=False, handle=CHANNEL_HANDLE,
                   verbose=True):
    """Run one incremental update pass.  Returns a summary dict."""
    if api_key is None:
        api_key = get_api_key()

    summary = {
        'new_videos': 0,
        'people_links': 0,
        'dog_links': 0,
        'episodes_assigned': 0,
        'stats_refreshed': 0,
        'unvalidated_tags': 0,
        'dry_run': dry_run,
    }

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        check_fts_triggers(cursor)

        existing_ids = {row[0] for row in cursor.execute('SELECT video_id FROM videos')}
        print(f'📀 Database: {db_path} ({len(existing_ids)} videos)')

        playlist_id = fetch_uploads_playlist_id(api_key, handle)
        print(f'📹 Uploads playlist: {playlist_id}')

        new_ids, seen_ids = discover_new_video_ids(
            api_key, playlist_id, existing_ids,
            full_scan=full_scan or do_refresh_stats, verbose=verbose,
        )
        print(f'🆕 New videos found: {len(new_ids)}')

        alias_to_authority = load_tag_authorities(TAG_AUTHORITY_PATH)

        # --- new videos -----------------------------------------------------
        new_rows = []
        for start in range(0, len(new_ids), PAGE_SIZE):
            batch = new_ids[start:start + PAGE_SIZE]
            for video in fetch_video_details(api_key, batch):
                new_rows.append(build_row(video, alias_to_authority))

        for row in new_rows:
            summary['unvalidated_tags'] += len(row['unvalidated_tags'])
            if dry_run:
                print(f'   [dry-run] would insert {row["video_id"]}: '
                      f'{row["title"][:60]} ({row["duration"]})')
                continue
            insert_video(cursor, row)
            summary['new_videos'] += 1
            print(f'   ➕ {row["video_id"]}: {row["title"][:60]} ({row["duration"]})')

        if dry_run:
            summary['new_videos'] = len(new_rows)
            print('   [dry-run] skipping enrichment + writes')
        elif new_rows:
            people_added, dogs_added = enrich_people_dogs(cursor, new_rows, verbose)
            summary['people_links'] = people_added
            summary['dog_links'] = dogs_added
            summary['episodes_assigned'] = assign_episodes(cursor, new_rows, verbose)

        # --- stats refresh for existing videos ------------------------------
        if do_refresh_stats and not dry_run:
            stale_ids = [vid for vid in seen_ids if vid in existing_ids]
            print(f'🔄 Refreshing stats for {len(stale_ids)} existing videos...')
            for start in range(0, len(stale_ids), PAGE_SIZE):
                batch = stale_ids[start:start + PAGE_SIZE]
                for video in fetch_video_details(api_key, batch):
                    row = build_row(video, alias_to_authority)
                    summary['stats_refreshed'] += refresh_stats(cursor, row)

        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    finally:
        conn.close()

    print('\n📊 UPDATE SUMMARY')
    print(f'   New videos:        {summary["new_videos"]}'
          + (' (dry run — nothing written)' if dry_run else ''))
    print(f'   People links added: {summary["people_links"]}')
    print(f'   Dog links added:    {summary["dog_links"]}')
    print(f'   Episodes assigned:  {summary["episodes_assigned"]}')
    if do_refresh_stats:
        print(f'   Stats refreshed:    {summary["stats_refreshed"]}')
    print(f'   Unvalidated tags on new videos: {summary["unvalidated_tags"]}'
          ' (review with review_unvalidated_tags.py)')

    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--db', default=DEFAULT_DB, help='SQLite database path')
    parser.add_argument('--dry-run', action='store_true',
                        help='report what would be added; write nothing')
    parser.add_argument('--full-scan', action='store_true',
                        help='walk the entire uploads playlist, not just until overlap')
    parser.add_argument('--refresh-stats', action='store_true',
                        help='also update view_count/like_count on existing videos')
    parser.add_argument('--handle', default=CHANNEL_HANDLE, help='channel handle')
    parser.add_argument('--quiet', action='store_true', help='less per-item output')
    args = parser.parse_args(argv)

    try:
        update_catalog(
            db_path=args.db,
            dry_run=args.dry_run,
            full_scan=args.full_scan,
            do_refresh_stats=args.refresh_stats,
            handle=args.handle,
            verbose=not args.quiet,
        )
    except RuntimeError as exc:
        print(f'❌ {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""Verification harness for scripts/update_catalog.py.

No API key is required: the three ``fetch_*`` functions are monkeypatched with
canned YouTube API payloads and the whole run is executed against a throwaway
copy of ``posa_wiki.db``.
"""

import importlib.util
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIVE_DB = REPO_ROOT / 'posa_wiki.db'


def _load_module():
    path = REPO_ROOT / 'scripts' / 'update_catalog.py'
    spec = importlib.util.spec_from_file_location('update_catalog_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


update_catalog = _load_module()


FAKE_EPISODE_ID = 'ZZTESTEPS99'
FAKE_PEOPLE_ID = 'ZZTESTLUC01'

FAKE_VIDEOS = {
    FAKE_EPISODE_ID: {
        'id': FAKE_EPISODE_ID,
        'snippet': {
            'title': 'The Unsuccessful Fishing Show - Episode 99',
            'publishedAt': '2026-08-01T12:00:00Z',
            'description': 'Another day of catching absolutely nothing.',
            'thumbnails': {'high': {'url': 'https://example.invalid/eps99.jpg'}},
            'tags': ['fishing', 'not-a-real-authority-tag'],
        },
        'contentDetails': {'duration': 'PT1H2M3S'},
        'statistics': {'viewCount': '1234', 'likeCount': '56'},
    },
    FAKE_PEOPLE_ID: {
        'id': FAKE_PEOPLE_ID,
        'snippet': {
            'title': 'Winter Camping Adventure',
            'publishedAt': '2026-08-05T12:00:00Z',
            'description': 'I went camping with Lucas and brought Layla along.',
            'thumbnails': {'high': {'url': 'https://example.invalid/winter.jpg'}},
            'tags': ['camping', 'zzz-unknown-tag'],
        },
        'contentDetails': {'duration': 'PT12M34S'},
        'statistics': {'viewCount': '999', 'likeCount': '99'},
    },
}


@pytest.fixture
def test_db(tmp_path):
    """A disposable copy of the live catalog database."""
    if not LIVE_DB.exists():
        pytest.skip('posa_wiki.db not present')
    copy = tmp_path / 'posa_wiki_copy.db'
    shutil.copy(LIVE_DB, copy)
    return str(copy)


@pytest.fixture
def mocked_api(monkeypatch, test_db):
    """Monkeypatch the API layer with a two-new-video uploads playlist."""
    with sqlite3.connect(test_db) as conn:
        existing = [row[0] for row in conn.execute(
            'SELECT video_id FROM videos ORDER BY upload_date DESC LIMIT 48'
        )]

    page_one = [FAKE_EPISODE_ID, FAKE_PEOPLE_ID] + existing
    calls = {'detail_batches': 0}

    def fake_playlist_id(api_key, handle=update_catalog.CHANNEL_HANDLE):
        return 'UUFAKEPLAYLIST'

    def fake_playlist_page(api_key, playlist_id, page_token=None):
        return page_one, None

    def fake_details(api_key, video_ids):
        calls['detail_batches'] += 1
        return [FAKE_VIDEOS[v] for v in video_ids if v in FAKE_VIDEOS]

    monkeypatch.setattr(update_catalog, 'fetch_uploads_playlist_id', fake_playlist_id)
    monkeypatch.setattr(update_catalog, 'fetch_playlist_page', fake_playlist_page)
    monkeypatch.setattr(update_catalog, 'fetch_video_details', fake_details)
    return calls


def _run(test_db, **kwargs):
    return update_catalog.update_catalog(
        db_path=test_db, api_key='test-key', verbose=False, **kwargs
    )


# ---------------------------------------------------------------------------
# API key handling
# ---------------------------------------------------------------------------

def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv('YOUTUBE_API_KEY', 'env-key')
    assert update_catalog.get_api_key() == 'env-key'


def test_api_key_from_api_md(monkeypatch, tmp_path):
    monkeypatch.delenv('YOUTUBE_API_KEY', raising=False)
    api_md = tmp_path / 'api.md'
    api_md.write_text('file-key\n')
    assert update_catalog.get_api_key(api_md_path=api_md) == 'file-key'


def test_api_key_missing_raises(monkeypatch, tmp_path):
    monkeypatch.delenv('YOUTUBE_API_KEY', raising=False)
    with pytest.raises(RuntimeError) as exc:
        update_catalog.get_api_key(api_md_path=tmp_path / 'nope.md')
    assert 'YOUTUBE_API_KEY' in str(exc.value)


# ---------------------------------------------------------------------------
# Insert / enrichment path
# ---------------------------------------------------------------------------

def test_new_videos_inserted_with_duration_and_tags(test_db, mocked_api):
    summary = _run(test_db)
    assert summary['new_videos'] == 2

    conn = sqlite3.connect(test_db)
    rows = {
        r[0]: r for r in conn.execute(
            'SELECT video_id, title, upload_date, duration, duration_seconds, '
            'view_count, like_count, youtube_tags, validated_tags, unvalidated_tags '
            'FROM videos WHERE video_id IN (?, ?)',
            (FAKE_EPISODE_ID, FAKE_PEOPLE_ID),
        )
    }
    assert set(rows) == {FAKE_EPISODE_ID, FAKE_PEOPLE_ID}

    eps = rows[FAKE_EPISODE_ID]
    assert eps[3] == '1:02:03'
    assert eps[4] == 3723
    assert eps[5] == 1234 and eps[6] == 56

    winter = rows[FAKE_PEOPLE_ID]
    assert winter[3] == '12:34'
    assert winter[4] == 754
    assert winter[2] == '2026-08-05'

    # Tag split against tag_authority_system.json
    assert json.loads(winter[7]) == ['camping', 'zzz-unknown-tag']
    assert json.loads(winter[8]) == ['Camping']
    assert json.loads(winter[9]) == ['zzz-unknown-tag']
    assert summary['unvalidated_tags'] >= 2
    conn.close()


def test_person_and_dog_links_created(test_db, mocked_api):
    summary = _run(test_db)
    conn = sqlite3.connect(test_db)

    people = [r[0] for r in conn.execute(
        'SELECT p.canonical_name FROM video_people vp '
        'JOIN people p ON p.person_id = vp.person_id WHERE vp.video_id = ?',
        (FAKE_PEOPLE_ID,),
    )]
    dogs = [r[0] for r in conn.execute(
        'SELECT d.name FROM video_dogs vd JOIN dogs d ON d.dog_id = vd.dog_id '
        'WHERE vd.video_id = ?', (FAKE_PEOPLE_ID,),
    )]
    conn.close()

    assert 'Lucas' in people
    assert 'Layla' in dogs
    assert summary['people_links'] >= 1
    assert summary['dog_links'] >= 1


def test_episode_row_created(test_db, mocked_api):
    summary = _run(test_db)
    conn = sqlite3.connect(test_db)
    row = conn.execute(
        'SELECT vv.part_number, vv.version_type, t.trip_name '
        'FROM video_versions vv JOIN trips t ON t.trip_id = vv.trip_id '
        'WHERE vv.video_id = ?', (FAKE_EPISODE_ID,),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == 99
    assert row[1] == 'episode'
    assert row[2] == 'The Unsuccessful Fishing Show'
    assert summary['episodes_assigned'] == 1


def test_second_run_is_idempotent(test_db, mocked_api):
    first = _run(test_db)
    assert first['new_videos'] == 2

    conn = sqlite3.connect(test_db)
    before = conn.execute('SELECT COUNT(*) FROM videos').fetchone()[0]
    before_versions = conn.execute('SELECT COUNT(*) FROM video_versions').fetchone()[0]
    conn.close()

    second = _run(test_db)
    assert second['new_videos'] == 0
    assert second['people_links'] == 0
    assert second['dog_links'] == 0
    assert second['episodes_assigned'] == 0

    conn = sqlite3.connect(test_db)
    assert conn.execute('SELECT COUNT(*) FROM videos').fetchone()[0] == before
    assert conn.execute(
        'SELECT COUNT(*) FROM video_versions').fetchone()[0] == before_versions
    conn.close()


def test_dry_run_writes_nothing(test_db, mocked_api):
    conn = sqlite3.connect(test_db)
    before = conn.execute('SELECT COUNT(*) FROM videos').fetchone()[0]
    conn.close()

    summary = _run(test_db, dry_run=True)
    assert summary['new_videos'] == 2
    assert summary['dry_run'] is True

    conn = sqlite3.connect(test_db)
    assert conn.execute('SELECT COUNT(*) FROM videos').fetchone()[0] == before
    assert conn.execute(
        'SELECT COUNT(*) FROM videos WHERE video_id = ?',
        (FAKE_EPISODE_ID,)).fetchone()[0] == 0
    conn.close()


def test_refresh_stats_updates_existing_only(test_db, mocked_api, monkeypatch):
    """--refresh-stats updates counters for videos already in the DB."""
    _run(test_db)

    conn = sqlite3.connect(test_db)
    conn.execute('UPDATE videos SET view_count = 0, like_count = 0 '
                 'WHERE video_id = ?', (FAKE_EPISODE_ID,))
    conn.commit()
    conn.close()

    summary = _run(test_db, do_refresh_stats=True)
    conn = sqlite3.connect(test_db)
    views, likes = conn.execute(
        'SELECT view_count, like_count FROM videos WHERE video_id = ?',
        (FAKE_EPISODE_ID,)).fetchone()
    conn.close()

    assert summary['new_videos'] == 0
    assert views == 1234 and likes == 56


def test_fts_triggers_present(test_db):
    conn = sqlite3.connect(test_db)
    assert update_catalog.check_fts_triggers(conn.cursor()) is True
    conn.close()


def test_mining_word_boundary_regex_is_live():
    """Regression guard for the r'\\\\b' double-escape bug."""
    import mine_video_descriptions as mining

    known_people, known_dogs, family_terms, common_names = mining.load_known_entities()
    high, medium, low = mining.analyze_description(
        'Erin came along and Layla swam. My brother Dave was there too.',
        known_people, known_dogs, family_terms, common_names,
    )
    assert ('erin', 'person', 'mentioned: erin') in high
    assert ('layla', 'dog', 'mentioned: layla') in high
    assert medium, 'medium-confidence family terms should no longer be dead code'
    assert low, 'low-confidence name scan should no longer be dead code'

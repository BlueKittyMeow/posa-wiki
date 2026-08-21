"""Series taxonomy: seeding, auto-assignment and the /series routes.

The scripts are run against the throwaway fixture database from
tests/conftest.py (never posa_wiki.db), then the real Flask app -- pointed at
that same database -- is exercised end to end.
"""

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
NOT_FOUND_MARKER = b"Lost in the Wilderness"


def _load(name):
    path = REPO_ROOT / 'scripts' / f'{name}.py'
    spec = importlib.util.spec_from_file_location(f'{name}_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_series = _load('seed_series')
assign_series = _load('assign_series')


@pytest.fixture(scope='module', autouse=True)
def seeded_series(seeded_db, tmp_path_factory):
    """Run both scripts once against the fixture database."""
    json_path = tmp_path_factory.mktemp('series') / 'candidates.json'
    seed_summary = seed_series.seed(seeded_db['path'], verbose=False)
    assign_summary = assign_series.assign(
        seeded_db['path'], str(json_path), verbose=False)
    return {
        'seed': seed_summary,
        'assign': assign_summary,
        'json_path': json_path,
    }


def _series_id(db_path, name):
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            'SELECT series_id FROM series WHERE name = ?', (name,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, f'series {name!r} missing'
    return row[0]


# ---------------------------------------------------------------------------
# seed_series.py
# ---------------------------------------------------------------------------

def test_seed_creates_canonical_series(seeded_db, seeded_series):
    conn = sqlite3.connect(seeded_db['path'])
    names = {r[0] for r in conn.execute('SELECT name FROM series')}
    conn.close()

    for expected in ('Winter Camping', 'Canoe Camping', 'Day Hiking',
                     'Backyard Adventures', 'Hike and Cook', 'Unboxing',
                     'Channel Updates', 'Giveaways',
                     'A Winter Camping Christmas Story',
                     'Unsuccessful Fishing Show', 'Community Content',
                     'Special Occasions'):
        assert expected in names


def test_seed_retires_season_series(seeded_db, seeded_series):
    conn = sqlite3.connect(seeded_db['path'])
    names = {r[0] for r in conn.execute('SELECT name FROM series')}
    conn.close()

    assert 'Spring Camping' not in names
    assert 'Fall Camping' not in names


def test_seed_is_idempotent(seeded_db, seeded_series):
    summary = seed_series.seed(seeded_db['path'], verbose=False)
    assert summary['series_inserted'] == 0
    assert summary['series_updated'] == 0
    assert summary['series_retired'] == 0
    assert summary['fishing_episodes_migrated'] == 0


# ---------------------------------------------------------------------------
# assign_series.py
# ---------------------------------------------------------------------------

def test_assign_populates_video_series(seeded_db, seeded_series):
    totals = seeded_series['assign']['totals_by_series']
    # "Quiet Canoe Morning" + "Boundary Waters Canoe Trip"
    assert totals['Canoe Camping'] == 2
    # "Boundary Waters Canoe Trip"
    assert totals['Boundary Waters'] == 1
    # "Ten Hour Winter Trek"
    assert totals['Winter Camping'] == 1


def test_assign_records_provenance_in_notes(seeded_db, seeded_series):
    conn = sqlite3.connect(seeded_db['path'])
    notes = {r[0] for r in conn.execute('SELECT notes FROM video_series')}
    conn.close()

    assert notes
    assert all(n and n.startswith(('auto:', 'migrated:')) for n in notes)


def test_assign_is_idempotent(seeded_db, seeded_series):
    summary = assign_series.assign(
        seeded_db['path'], str(seeded_series['json_path']), verbose=False)
    assert summary['inserted_total'] == 0


def test_assign_writes_review_candidates_json(seeded_series):
    payload = json.loads(seeded_series['json_path'].read_text())
    assert payload['count'] == len(payload['candidates'])
    for candidate in payload['candidates']:
        assert candidate['confidence'] == 'medium'
        assert candidate['proposed_series']
        assert candidate['rule']


def test_community_child_implies_umbrella():
    """A child membership always writes the umbrella row too."""
    row = {
        'title': 'Hike and Cook - 5k Subscribers Giveaway!',
        'description': '',
        'youtube_tags': None,
        'upload_date': '2018-02-25',
    }
    high, _ = assign_series.classify(row)
    names = {name for name, _, _ in high}
    assert 'Giveaways' in names
    assert 'Community Content' in names
    assert 'Hike and Cook' in names
    assert 'Day Hiking' in names


def test_christmas_story_episode_numbers():
    first, _ = assign_series.classify({
        'title': 'A Winter Camping Christmas Story',
        'description': '', 'youtube_tags': None, 'upload_date': '2017-12-24',
    })
    sixth, _ = assign_series.classify({
        'title': 'Hot Tenting In A Snowstorm - A Winter Camping Christmas Story 6',
        'description': '', 'youtube_tags': None, 'upload_date': '2022-12-25',
    })
    episodes = {name: ep for name, ep, _ in first}
    assert episodes['A Winter Camping Christmas Story'] == 1
    episodes = {name: ep for name, ep, _ in sixth}
    assert episodes['A Winter Camping Christmas Story'] == 6


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def test_series_list_shows_populated_series(client, seeded_series):
    response = client.get('/series')
    assert response.status_code == 200
    assert b'Canoe Camping' in response.data
    # grouping headers
    assert b'Adventure Types' in response.data
    assert b'Places' in response.data
    # member count rendered
    assert b'2 videos' in response.data


def test_series_list_hides_empty_series(client, seeded_series):
    response = client.get('/series')
    assert b'Backpacking' not in response.data


def test_series_detail_returns_200(client, seeded_db, seeded_series):
    series_id = _series_id(seeded_db['path'], 'Canoe Camping')
    response = client.get(f'/series/{series_id}')
    assert response.status_code == 200
    assert b'Quiet Canoe Morning' in response.data
    assert b'Boundary Waters Canoe Trip' in response.data


def test_series_detail_404_themed(client, seeded_series):
    response = client.get('/series/999999')
    assert response.status_code == 404
    assert NOT_FOUND_MARKER in response.data


def test_homepage_series_buttons_are_real_links(client, seeded_db,
                                                seeded_series):
    response = client.get('/')
    assert response.status_code == 200

    body = response.data.decode()
    for name in ('Winter Camping', 'Canoe Camping',
                 'Unsuccessful Fishing Show'):
        expected = f'/series/{_series_id(seeded_db["path"], name)}"'
        assert expected in body, f'no link for {name}'

    # the three browse buttons used to be href="#" placeholders
    for label in ('❄️ Winter Camping', '🛶 Canoe Adventures',
                  '🎣 Fishing Videos'):
        assert f'href="#" class="btn btn-secondary">{label}' not in body


def test_video_detail_lists_series_memberships(client, seeded_db,
                                               seeded_series):
    series_id = _series_id(seeded_db['path'], 'Canoe Camping')
    response = client.get(f'/video/{seeded_db["video_id"]}')
    assert response.status_code == 200
    assert f'/series/{series_id}"'.encode() in response.data


def test_trips_still_lists_real_trips(client, seeded_db, seeded_series):
    response = client.get('/trips')
    assert response.status_code == 200
    assert b'Boundary Waters Trip' in response.data
    # The Fishing Show is a series now: no trip row survives the migration
    conn = sqlite3.connect(seeded_db['path'])
    trips = {r[0] for r in conn.execute('SELECT trip_name FROM trips')}
    conn.close()
    assert 'The Unsuccessful Fishing Show' not in trips

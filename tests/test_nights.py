"""Tests for the trip-length (nights) facet (Phase 2B).

Deliberately the same shape as ``tests/test_seasons.py``, in three layers:

* the rules in ``scripts/derive_nights.py`` -- including the things they must
  *refuse* to do (infer 0, resolve a days/nights disagreement, overwrite a
  human);
* the ``nights`` review queue end to end;
* the site surfacing -- ``/videos?nights=…`` filtering and the detail badge.

Trip length is a video facet, and **Unknown (NULL) is a legitimate value**.
Several tests exist purely to pin that down: a Hike and Cook video is
*probably* a day trip, and "probably" must stay a proposal rather than
becoming a 0 in the database.
"""

import importlib
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.conftest import _apply_migrations, _run_create_database  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

ADMIN_USERNAME = 'nights-admin'
ADMIN_PASSWORD = 'nights-password'


# ---------------------------------------------------------------------------
# rule unit tests -- no database, no Flask
# ---------------------------------------------------------------------------

def _row(title, description='', nights=None, confidence=None):
    """A dict standing in for a sqlite3.Row (both support ``[]`` + ``.keys()``)."""
    class _Row(dict):
        def keys(self):  # sqlite3.Row-compatible
            return list(super().keys())

    return _Row(title=title, description=description,
                number_of_nights=nights, nights_confidence=confidence,
                video_id='vid_x', upload_date='2024-01-01')


@pytest.fixture(scope='module')
def derive_module():
    sys.path.insert(0, str(REPO_ROOT / 'scripts'))
    return importlib.import_module('scripts.derive_nights')


def test_stated_nights_are_exact(derive_module):
    high, review = derive_module.classify(
        _row('7 Nights Of Winter Camping On The Ice'))
    assert high is not None
    nights, source, _evidence = high
    assert nights == 7
    assert source == 'title:nights'
    assert review == []


def test_stated_nights_variants(derive_module):
    for title, expected in (
            ('Winter Camping In A Hot Tent With My Dogs For 2 Nights', 2),
            ('3 Night Fall Wilderness Adventure', 3),
            ('7  Night Canoe Adventure [Full Trip]', 7),   # his own double space
            ('12 Nights in the Wilderness With a Puppy', 12),
            ('5 Night Wilderness Adventure', 5)):
        high, _review = derive_module.classify(_row(title))
        assert high is not None and high[0] == expected, title


def test_night_x_of_y_gives_the_trip_length(derive_module):
    """'(Night 2 of 7)' is a part title: the trip is 7 nights, not 2."""
    high, _review = derive_module.classify(
        _row('7 Night Wilderness Adventure (Night 2 of 7)'))
    assert high[0] == 7
    assert high[1].startswith('title:night-of')


def test_days_convert_to_nights_minus_one(derive_module):
    high, review = derive_module.classify(
        _row('10 Days (Almost) Alone in the Wilderness - Part 3 of 3'))
    assert high == (9, 'title:days-minus-one', high[2])
    assert review == []


def test_days_and_nights_consistent_is_written(derive_module):
    """His own cross-check case: 8 Day … (Night 7 of 7) -> 7 nights."""
    high, review = derive_module.classify(
        _row('8 Day Wilderness Adventure with My Dog (Night 7 of 7) '
             '[Extended Version]'))
    assert high is not None
    nights, source, _evidence = high
    assert nights == 7
    assert 'cross-check' in source
    assert review == []


def test_days_and_nights_inconsistent_goes_to_review(derive_module):
    """A disagreement is never resolved by picking a side."""
    high, review = derive_module.classify(
        _row('10 Day Wilderness Adventure (Night 7 of 7)'))
    assert high is None, 'an inconsistent title must not be auto-written'
    proposed = {(nights, rule) for nights, rule, _e in review}
    assert (7, 'conflict:title:night-of') in proposed
    assert (9, 'conflict:title:days-minus-one') in proposed


def test_overnight_is_one_night(derive_module):
    for title in ('Overnight Camping With My Dog',
                  'Winter Camping Overnighter - Wild Game Surf and Turf',
                  'Early Fall Overnighter With My Dogs'):
        high, _review = derive_module.classify(_row(title))
        assert high is not None and high[0] == 1, title
        assert high[1] == 'title:overnight'


def test_a_stated_count_beats_overnight(derive_module):
    high, _review = derive_module.classify(
        _row('Overnight Camping Compilation - 3 Nights Out'))
    assert high[0] == 3


def test_day_trip_series_only_proposes_zero(derive_module):
    """A Hike and Cook is *probably* 0 nights -- probably is not a write."""
    high, review = derive_module.classify(
        _row('Hike and Cook - The Dog Days of Summer'),
        in_day_trip_series=True)
    assert high is None, '0 must never be inferred'
    assert [(n, r) for n, r, _e in review] == [(0, 'series:day-trip')]


def test_day_trip_series_without_membership_proposes_nothing(derive_module):
    high, review = derive_module.classify(
        _row('Hike and Cook - The Dog Days of Summer'))
    assert high is None and review == []


def test_week_language_is_medium_only(derive_module):
    """A 'week' is 6 or 7 nights and the title does not say which."""
    high, review = derive_module.classify(
        _row('Weeklong Autumn Adventure in the Wilderness'))
    assert high is None
    assert [(n, r) for n, r, _e in review] == [(7, 'title:week-language')]

    high, review = derive_module.classify(
        _row('2 Weeks On Isle Royal In Lake Superior'))
    assert high is None
    assert review[0][0] == 14


def test_description_evidence_is_medium_only(derive_module):
    high, review = derive_module.classify(
        _row('Monty\'s First Camping Trip',
             description='We spent 2 nights out in the wilderness.'))
    assert high is None
    assert (2, 'description:nights') in [(n, r) for n, r, _e in review]


def test_description_beyond_the_window_is_ignored(derive_module):
    padding = 'gear links and sponsor copy. ' * 40
    assert len(padding) > derive_module.DESCRIPTION_WINDOW
    high, review = derive_module.classify(
        _row('A Trip', description=padding + 'we spent 4 nights out'))
    assert high is None and review == []


def test_ambiguous_video_stays_unknown(derive_module):
    """No length evidence means Unknown -- never a plausible-sounding guess."""
    high, review = derive_module.classify(
        _row('Wednesday Chit Chat - Giveaway Update',
             description='Thanks for watching, see you Sunday.'))
    assert high is None
    assert review == []


def test_a_lone_night_word_is_not_a_count(derive_module):
    high, review = derive_module.classify(
        _row('A Crackling Campfire During A Windy Winter Night - ASMR'))
    assert high is None and review == []


def test_implausible_counts_are_refused(derive_module):
    high, review = derive_module.classify(_row('365 Nights In The Woods'))
    assert high is None and review == []


def test_one_day_does_not_write_zero(derive_module):
    """'1 Day' converts to 0, and 0 is only ever proposed."""
    high, review = derive_module.classify(_row('1 Day Wilderness Adventure'))
    assert high is None
    assert [(n, r) for n, r, _e in review] == [(0, 'title:days-minus-one')]


# ---------------------------------------------------------------------------
# derive() against a real database
# ---------------------------------------------------------------------------

@pytest.fixture()
def nights_db(tmp_path_factory):
    """Throwaway database seeded with one video per interesting case."""
    scratch = tmp_path_factory.mktemp('posa_nights_db')
    db_path = _run_create_database(scratch)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        _apply_migrations(conn)
        videos = [
            ('vid_nights', '7 Nights Of Winter Camping On The Ice', '2024-02-01'),
            ('vid_cross', '8 Day Wilderness Adventure with My Dog '
                          '(Night 7 of 7)', '2024-08-01'),
            ('vid_days', '10 Days (Almost) Alone in the Wilderness', '2024-09-01'),
            ('vid_overnight', 'Overnight Camping With My Dogs', '2024-03-01'),
            ('vid_conflict', '10 Day Wilderness Adventure (Night 7 of 7)',
             '2024-06-01'),
            ('vid_week', 'Weeklong Autumn Adventure in the Wilderness',
             '2024-10-01'),
            ('vid_unknown', 'Wednesday Chit Chat - Giveaway Update', '2024-05-01'),
        ]
        for video_id, title, upload_date in videos:
            conn.execute(
                'INSERT INTO videos (video_id, title, upload_date, '
                'thumbnail_url, youtube_tags) VALUES (?, ?, ?, ?, ?)',
                (video_id, title, upload_date,
                 f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg',
                 json.dumps([])))
        conn.commit()
    finally:
        conn.close()
    return db_path


def _nights(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return {row['video_id']: (row['number_of_nights'],
                                  row['nights_confidence'],
                                  row['nights_source'])
                for row in conn.execute(
                    'SELECT video_id, number_of_nights, nights_confidence, '
                    'nights_source FROM videos')}
    finally:
        conn.close()


def test_derive_writes_high_confidence_only(derive_module, nights_db, tmp_path):
    result = derive_module.derive(
        str(nights_db), json_path=str(tmp_path / 'candidates.json'),
        verbose=False, decisions_path=str(tmp_path / 'decisions.json'))

    nights = _nights(nights_db)
    assert nights['vid_nights'] == (7, 'high', 'title:nights')
    assert nights['vid_days'] == (9, 'high', 'title:days-minus-one')
    assert nights['vid_overnight'] == (1, 'high', 'title:overnight')
    assert nights['vid_cross'][0] == 7
    assert 'cross-check' in nights['vid_cross'][2]
    # Unknown is a legitimate value: inconsistent, week-language and
    # evidence-free videos are all left alone.
    assert nights['vid_conflict'][0] is None
    assert nights['vid_week'][0] is None
    assert nights['vid_unknown'][0] is None
    assert result['written_total'] == 4
    assert result['unknown'] == 3


def test_derive_is_idempotent(derive_module, nights_db, tmp_path):
    kwargs = dict(json_path=str(tmp_path / 'candidates.json'), verbose=False,
                  decisions_path=str(tmp_path / 'decisions.json'))
    first = derive_module.derive(str(nights_db), **kwargs)
    before = _nights(nights_db)
    second = derive_module.derive(str(nights_db), **kwargs)

    assert first['written_total'] == 4
    assert second['written_total'] == 0, 'a second run must write nothing'
    assert _nights(nights_db) == before


def test_derive_never_overwrites_a_human_value(derive_module, nights_db,
                                               tmp_path):
    conn = sqlite3.connect(nights_db)
    conn.execute(
        "UPDATE videos SET number_of_nights = 2, nights_confidence = 'human', "
        "nights_source = 'human:web-review' WHERE video_id = 'vid_nights'")
    conn.commit()
    conn.close()

    derive_module.derive(str(nights_db),
                         json_path=str(tmp_path / 'candidates.json'),
                         verbose=False,
                         decisions_path=str(tmp_path / 'decisions.json'))

    # The title says 7 nights; the human said 2. The human wins.
    assert _nights(nights_db)['vid_nights'] == (2, 'human', 'human:web-review')


def test_derive_leaves_an_existing_value_alone(derive_module, nights_db,
                                               tmp_path):
    """High-confidence values are only re-derived when the length is NULL."""
    conn = sqlite3.connect(nights_db)
    conn.execute("UPDATE videos SET number_of_nights = 4, nights_confidence = "
                 "'high', nights_source = 'title:nights' "
                 "WHERE video_id = 'vid_nights'")
    conn.commit()
    conn.close()

    result = derive_module.derive(
        str(nights_db), json_path=str(tmp_path / 'candidates.json'),
        verbose=False, decisions_path=str(tmp_path / 'decisions.json'))

    assert _nights(nights_db)['vid_nights'][0] == 4
    assert result['skipped_existing'] == 1


def test_derive_dumps_review_candidates(derive_module, nights_db, tmp_path):
    json_path = tmp_path / 'candidates.json'
    derive_module.derive(str(nights_db), json_path=str(json_path),
                         verbose=False,
                         decisions_path=str(tmp_path / 'decisions.json'))

    payload = json.loads(json_path.read_text())
    proposed = {(c['video_id'], c['proposed_nights'])
                for c in payload['candidates']}
    assert ('vid_conflict', 7) in proposed
    assert ('vid_conflict', 9) in proposed
    assert ('vid_week', 7) in proposed
    assert not any(c['video_id'] == 'vid_unknown'
                   for c in payload['candidates'])
    assert all(c['evidence'] for c in payload['candidates'])


def test_derive_skips_already_decided_videos(derive_module, nights_db, tmp_path):
    decisions_path = tmp_path / 'decisions.json'
    decisions_path.write_text(json.dumps({'decisions': {
        'vid_conflict': {'video_id': 'vid_conflict', 'nights': 7,
                         'decision': 'reject'},
        'vid_week': {'video_id': 'vid_week', 'nights': 7,
                     'decision': 'reject'},
    }}))

    result = derive_module.derive(
        str(nights_db), json_path=str(tmp_path / 'candidates.json'),
        verbose=False, decisions_path=str(decisions_path))

    assert result['review_candidates'] == 0
    assert result['already_decided_skipped'] == 3


def test_dry_run_writes_nothing(derive_module, nights_db, tmp_path):
    json_path = tmp_path / 'candidates.json'
    derive_module.derive(str(nights_db), json_path=str(json_path),
                         dry_run=True, verbose=False,
                         decisions_path=str(tmp_path / 'decisions.json'))
    assert all(value[0] is None for value in _nights(nights_db).values())
    assert not json_path.exists()


# ---------------------------------------------------------------------------
# review queue + site surfacing (Flask)
# ---------------------------------------------------------------------------

def _write_nights_candidates(data_dir, db_path):
    payload = {
        'generated_at': '2026-08-24T00:00:00',
        'database': str(db_path),
        'count': 4,
        'note': 'test fixture',
        'candidates': [
            {'video_id': 'vid_conflict',
             'title': '10 Day Wilderness Adventure (Night 7 of 7)',
             'upload_date': '2024-06-01', 'proposed_nights': 7,
             'rule': 'conflict:title:night-of', 'evidence': 'Night 7 of 7',
             'confidence': 'medium'},
            {'video_id': 'vid_hike', 'title': 'Hike and Cook - Monty Birthday',
             'upload_date': '2024-04-01', 'proposed_nights': 0,
             'rule': 'series:day-trip',
             'evidence': 'member of a day-trip series', 'confidence': 'medium'},
            # Already has a high-confidence length -> must not be offered.
            {'video_id': 'vid_nights',
             'title': '7 Nights Of Winter Camping On The Ice',
             'upload_date': '2024-02-01', 'proposed_nights': 3,
             'rule': 'description:nights', 'evidence': '3 nights',
             'confidence': 'medium'},
            # Not a plausible trip length -> must be ignored outright.
            {'video_id': 'vid_unknown', 'title': 'Wednesday Chit Chat',
             'upload_date': '2024-05-01', 'proposed_nights': 900,
             'rule': 'made-up', 'evidence': 'nonsense', 'confidence': 'medium'},
        ],
    }
    path = Path(data_dir) / 'nights_review_candidates.json'
    path.write_text(json.dumps(payload, indent=2))
    return path


@pytest.fixture(scope='module')
def nights_env(tmp_path_factory):
    scratch = tmp_path_factory.mktemp('posa_nights_app_db')
    db_path = _run_create_database(scratch)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        _apply_migrations(conn)
        videos = [
            ('vid_nights', '7 Nights Of Winter Camping On The Ice',
             '2024-02-01', 7, 'high', 'title:nights'),
            ('vid_epic', '12 Nights in the Wilderness With a Puppy',
             '2024-07-01', 12, 'high', 'title:nights'),
            ('vid_overnight', 'Overnight Camping With My Dogs', '2024-03-01',
             1, 'high', 'title:overnight'),
            ('vid_daytrip', 'Hike and Cook - The Dog Days of Summer',
             '2024-08-01', 0, 'human', 'human:web-review'),
            ('vid_conflict', '10 Day Wilderness Adventure (Night 7 of 7)',
             '2024-06-01', None, None, None),
            ('vid_hike', 'Hike and Cook - Monty Birthday', '2024-04-01',
             None, None, None),
            ('vid_unknown', 'Wednesday Chit Chat', '2024-05-01',
             None, None, None),
        ]
        for video_id, title, date, nights, conf, source in videos:
            conn.execute(
                'INSERT INTO videos (video_id, title, upload_date, '
                'thumbnail_url, youtube_tags, number_of_nights, '
                'nights_confidence, nights_source) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (video_id, title, date,
                 f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg',
                 json.dumps([]), nights, conf, source))
        from models.user import User
        User.create(ADMIN_USERNAME, 'nights-admin@test.local', ADMIN_PASSWORD,
                    role='admin', db_conn=conn)
        conn.commit()
    finally:
        conn.close()

    data_dir = tmp_path_factory.mktemp('posa_nights_data')
    _write_nights_candidates(data_dir, db_path)

    return {'db_path': str(db_path), 'data_dir': str(data_dir)}


@pytest.fixture(scope='module')
def nights_app(nights_env):
    os.environ['DATABASE_PATH'] = nights_env['db_path']
    os.environ['DATA_DIR'] = nights_env['data_dir']
    os.environ['POSA_WIKI_ENV'] = 'testing'
    os.environ['RATELIMIT_ENABLED'] = 'false'

    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])
    if 'app' in sys.modules:
        app_module = importlib.reload(sys.modules['app'])
    else:
        app_module = importlib.import_module('app')

    flask_app = app_module.app
    assert flask_app.config['DATABASE_PATH'] == nights_env['db_path']
    flask_app.config['WTF_CSRF_ENABLED'] = False

    yield flask_app

    for key in ('DATA_DIR', 'RATELIMIT_ENABLED'):
        os.environ.pop(key, None)
    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])


@pytest.fixture(scope='module')
def nights_client(nights_app):
    client = nights_app.test_client()
    response = client.post('/auth/login', data={
        'username': ADMIN_USERNAME, 'password': ADMIN_PASSWORD,
    }, follow_redirects=True)
    assert response.status_code == 200
    return client


@pytest.fixture()
def anon(nights_app):
    return nights_app.test_client()


def _db(app):
    conn = sqlite3.connect(app.config['DATABASE_PATH'])
    conn.row_factory = sqlite3.Row
    return conn


# -- queue ------------------------------------------------------------------

def test_nights_queue_is_registered():
    from services.review_service import QUEUES
    assert 'nights' in QUEUES


def test_dashboard_counts_the_nights_queue(nights_client):
    body = nights_client.get('/admin/').get_data(as_text=True)
    assert 'Trip length candidates' in body


def test_nights_queue_lists_only_actionable_candidates(nights_client):
    response = nights_client.get('/admin/review/nights')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '10 Day Wilderness Adventure' in body      # inconsistent, still NULL
    assert 'Hike and Cook - Monty Birthday' in body   # day-trip series proposal
    # Already carries a high-confidence length -> not up for review.
    assert '7 Nights Of Winter Camping On The Ice' not in body
    # 900 nights is not a trip.
    assert 'Wednesday Chit Chat' not in body


def test_nights_queue_shows_evidence(nights_client):
    body = nights_client.get('/admin/review/nights').get_data(as_text=True)
    assert 'member of a day-trip series' in body
    assert 'series:day-trip' in body


def test_approve_writes_a_human_value(nights_app, nights_client, nights_env):
    response = nights_client.post(
        '/admin/review/nights/approve',
        data={'payload': json.dumps({'video_id': 'vid_conflict',
                                     'nights': 7})},
        follow_redirects=True)
    assert response.status_code == 200

    conn = _db(nights_app)
    try:
        row = conn.execute(
            'SELECT number_of_nights, nights_confidence, nights_source '
            "FROM videos WHERE video_id = 'vid_conflict'").fetchone()
    finally:
        conn.close()
    assert row['number_of_nights'] == 7
    assert row['nights_confidence'] == 'human'
    assert row['nights_source'] == 'human:web-review'

    decisions = json.loads(
        (Path(nights_env['data_dir']) / 'nights_review_decisions.json')
        .read_text())['decisions']
    assert decisions['vid_conflict']['decision'] == 'approve'

    # ...and the card is gone.
    body = nights_client.get('/admin/review/nights').get_data(as_text=True)
    assert '10 Day Wilderness Adventure' not in body


def test_approving_zero_nights_is_allowed(nights_app, nights_client):
    """0 is a real value (a day trip) -- a human may certainly choose it."""
    response = nights_client.post(
        '/admin/review/nights/approve',
        data={'payload': json.dumps({'video_id': 'vid_hike', 'nights': 0})},
        follow_redirects=True)
    assert response.status_code == 200

    conn = _db(nights_app)
    try:
        row = conn.execute(
            'SELECT number_of_nights, nights_confidence FROM videos '
            "WHERE video_id = 'vid_hike'").fetchone()
    finally:
        conn.close()
    assert row['number_of_nights'] == 0
    assert row['nights_confidence'] == 'human'


def test_reject_records_the_decision_without_touching_the_video(
        nights_app, nights_env):
    from services.review_service import NightsCandidateQueue
    conn = _db(nights_app)
    try:
        with nights_app.app_context():
            NightsCandidateQueue().reject(
                conn, {'video_id': 'vid_unknown', 'nights': 3})
        row = conn.execute(
            'SELECT number_of_nights, nights_confidence FROM videos '
            "WHERE video_id = 'vid_unknown'").fetchone()
    finally:
        conn.close()
    # Rejecting means "Unknown stands".
    assert row['number_of_nights'] is None
    assert row['nights_confidence'] is None

    decisions = json.loads(
        (Path(nights_env['data_dir']) / 'nights_review_decisions.json')
        .read_text())['decisions']
    assert decisions['vid_unknown']['decision'] == 'reject'


def test_approving_an_implausible_length_is_refused(nights_app):
    from services.review_service import NightsCandidateQueue
    conn = _db(nights_app)
    try:
        with pytest.raises(ValueError):
            NightsCandidateQueue().approve(
                conn, {'video_id': 'vid_unknown', 'nights': 900})
        with pytest.raises(ValueError):
            NightsCandidateQueue().approve(
                conn, {'video_id': 'vid_unknown', 'nights': 'sevenish'})
    finally:
        conn.close()


def test_queue_requires_login(anon):
    response = anon.get('/admin/review/nights')
    assert response.status_code == 302
    assert '/auth/login' in response.headers['Location']


# -- site surfacing ---------------------------------------------------------

def test_videos_epic_filter(anon):
    body = anon.get('/videos?nights=epic').get_data(as_text=True)
    assert '12 Nights in the Wilderness' in body
    assert 'Overnight Camping With My Dogs' not in body


def test_videos_nights_buckets(anon):
    overnight = anon.get('/videos?nights=overnight').get_data(as_text=True)
    assert 'Overnight Camping With My Dogs' in overnight
    assert '12 Nights in the Wilderness' not in overnight

    week = anon.get('/videos?nights=week').get_data(as_text=True)
    assert '7 Nights Of Winter Camping On The Ice' in week
    assert '12 Nights in the Wilderness' not in week

    day = anon.get('/videos?nights=day').get_data(as_text=True)
    assert 'Hike and Cook - The Dog Days of Summer' in day
    assert 'Overnight Camping With My Dogs' not in day


def test_videos_unknown_filter_selects_nulls(anon):
    body = anon.get('/videos?nights=unknown').get_data(as_text=True)
    assert 'Wednesday Chit Chat' in body
    assert '12 Nights in the Wilderness' not in body


def test_videos_bogus_nights_is_ignored(anon):
    response = anon.get('/videos?nights=fortnight')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '12 Nights in the Wilderness' in body
    assert 'Wednesday Chit Chat' in body


def test_nights_chip_row_renders_with_counts(anon):
    body = anon.get('/videos').get_data(as_text=True)
    assert 'nights-filter' in body
    for label in ('🥾 Day trip', '🌙 Overnight', '⛺ Weekend', '🏕️ Week-ish',
                  '🗺️ Epic'):
        assert label in body


def test_nights_filter_preserves_season_and_sort_params(anon):
    body = anon.get('/videos?season=unknown&sort=title&order=asc').get_data(
        as_text=True)
    assert 'sort=title' in body and 'order=asc' in body
    # Every trip-length chip carries the active season filter along with it.
    assert 'nights=epic' in body
    assert 'season=unknown' in body


def test_nights_and_season_filters_compose(anon):
    response = anon.get('/videos?season=unknown&nights=epic')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    # vid_epic has no season, so it survives both filters.
    assert '12 Nights in the Wilderness' in body
    assert 'Overnight Camping With My Dogs' not in body


def test_detail_page_renders_the_nights_badge(anon):
    body = anon.get('/video/vid_nights').get_data(as_text=True)
    assert 'nights-chip' in body
    assert '🌙 7 nights' in body


def test_detail_page_renders_day_trip_for_zero(anon):
    body = anon.get('/video/vid_daytrip').get_data(as_text=True)
    assert 'nights-chip' in body
    assert '🥾 Day trip' in body


def test_detail_page_omits_the_badge_when_unknown(anon):
    body = anon.get('/video/vid_unknown').get_data(as_text=True)
    assert 'nights-chip' not in body


def test_watch_page_renders_the_nights_badge(anon):
    body = anon.get('/watch/vid_overnight').get_data(as_text=True)
    assert '🌙 1 night' in body

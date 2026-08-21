"""Tests for the season facet (Phase 2B).

Three layers:

* the rules in ``scripts/derive_seasons.py`` -- including the things they must
  *refuse* to do (guess, overwrite a human, resolve a conflict);
* the ``seasons`` review queue end to end (mirrors ``tests/test_admin_review.py``);
* the site surfacing -- ``/videos?season=…`` filtering and the detail badge.

Seasons are a video facet, not a series, and **Unknown (NULL) is a legitimate
value**. Several tests exist purely to pin that down: an ambiguous canoe video
must stay Unknown rather than acquire a plausible-looking season.
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

ADMIN_USERNAME = 'season-admin'
ADMIN_PASSWORD = 'season-password'


# ---------------------------------------------------------------------------
# rule unit tests -- no database, no Flask
# ---------------------------------------------------------------------------

def _row(title, description='', tags=None, season=None, confidence=None):
    """A dict standing in for a sqlite3.Row (both support ``[]`` + ``.keys()``)."""
    class _Row(dict):
        def keys(self):  # sqlite3.Row-compatible
            return list(super().keys())

    return _Row(title=title, description=description,
                youtube_tags=json.dumps(tags or []),
                season=season, season_confidence=confidence,
                video_id='vid_x', upload_date='2024-01-01')


@pytest.fixture(scope='module')
def derive_module():
    sys.path.insert(0, str(REPO_ROOT / 'scripts'))
    return importlib.import_module('scripts.derive_seasons')


def test_winter_title_is_high_confidence(derive_module):
    high, review = derive_module.classify(
        _row('7 Nights Of Winter Camping On The Ice'))
    assert high is not None
    season, source, _evidence = high
    assert season == 'winter'
    assert source == 'title:winter'
    assert review == []


def test_winter_synonyms_all_match(derive_module):
    for title in ('Hot Tenting In The Snow', 'Building A Quinzee',
                  'Caught In A Blizzard', 'Ice Fishing With My Dogs',
                  'Snowstorm Overnighter'):
        high, _review = derive_module.classify(_row(title))
        assert high is not None and high[0] == 'winter', title


def test_spring_title_is_high_confidence(derive_module):
    high, review = derive_module.classify(_row('Spring Bushcraft Camp With My Dog'))
    assert high == ('spring', 'title:spring', high[2])
    assert review == []


def test_summer_and_fall_titles(derive_module):
    high, _ = derive_module.classify(_row('Summer Fishing Catch and Cook'))
    assert high[0] == 'summer'
    high, _ = derive_module.classify(_row('Weeklong Autumn Adventure'))
    assert high[0] == 'fall'


def test_conflict_goes_to_review_and_is_never_written(derive_module):
    """Two seasons in one title resolves to nothing, not to a coin flip."""
    high, review = derive_module.classify(_row('Spring Snowstorm In A Hot Tent'))
    assert high is None, 'a conflicted video must not be auto-written'
    proposed = {season for season, _rule, _evidence in review}
    assert proposed == {'winter', 'spring'}
    assert all(rule.startswith('conflict:') for _s, rule, _e in review)


def test_ambiguous_video_stays_unknown(derive_module):
    """No evidence means Unknown -- never a plausible-sounding guess."""
    high, review = derive_module.classify(
        _row('7 Night Canoe Adventure [Full Trip]',
             description='Seven nights out on the water with the dogs.'))
    assert high is None
    assert review == []


def test_upload_date_is_not_evidence(derive_module):
    """Uploads lag filming, so the date must never drive the season."""
    high, review = derive_module.classify(
        _row('Overnight Camping With My Dogs'))
    assert high is None and review == []


def test_winter_tag_alone_is_only_a_proposal(derive_module):
    """The 'winter camping' tag is channel SEO boilerplate, not evidence."""
    high, review = derive_module.classify(
        _row('Overnight Camping With My Dogs - The Monty Returns',
             tags=['winter camping', 'camping', 'bushcraft']))
    assert high is None, 'a boilerplate tag must not auto-write a season'
    assert [(s, r) for s, r, _e in review] == [('winter', 'tag:winter camping')]


def test_winter_tag_suppressed_when_title_contradicts(derive_module):
    """Open water contradicts ice: not even worth proposing."""
    high, review = derive_module.classify(
        _row('7 Night Canoe Adventure', tags=['winter camping', 'camping']))
    assert high is None
    assert review == []


def test_title_beats_tag(derive_module):
    high, _review = derive_module.classify(
        _row('A Beautiful Fall Hike', tags=['winter camping']))
    assert high[0] == 'fall'


def test_holiday_is_medium_only(derive_module):
    high, review = derive_module.classify(_row('Halloween Camping Trip'))
    assert high is None
    assert ('fall', 'title:holiday-fall') in [(s, r) for s, r, _e in review]


def test_description_keyword_is_medium_only(derive_module):
    high, review = derive_module.classify(
        _row('An Overnight With The Dogs',
             description='We got caught in a snowstorm out there.'))
    assert high is None
    assert ('winter', 'description:winter') in [(s, r) for s, r, _e in review]


def test_description_beyond_the_window_is_ignored(derive_module):
    padding = 'gear links and sponsor copy. ' * 40
    assert len(padding) > derive_module.DESCRIPTION_WINDOW
    high, review = derive_module.classify(
        _row('An Overnight With The Dogs', description=padding + 'snowstorm'))
    assert high is None and review == []


# ---------------------------------------------------------------------------
# derive() against a real database
# ---------------------------------------------------------------------------

@pytest.fixture()
def season_db(tmp_path_factory):
    """Throwaway database seeded with one video per interesting case."""
    scratch = tmp_path_factory.mktemp('posa_seasons_db')
    db_path = _run_create_database(scratch)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        _apply_migrations(conn)
        videos = [
            ('vid_winter', 'Winter Camping In A Hot Tent', '2024-02-01', []),
            ('vid_spring', 'Spring Canoe Camping With The Dogs', '2024-05-01', []),
            ('vid_conflict', 'Spring Snowstorm In A Hot Tent', '2024-04-01', []),
            ('vid_unknown', '7 Night Canoe Adventure [Full Trip]',
             '2024-07-01', []),
            ('vid_tagonly', 'Overnight Camping With My Dogs', '2024-03-01',
             ['winter camping', 'bushcraft']),
        ]
        for video_id, title, upload_date, tags in videos:
            conn.execute(
                'INSERT INTO videos (video_id, title, upload_date, '
                'thumbnail_url, youtube_tags) VALUES (?, ?, ?, ?, ?)',
                (video_id, title, upload_date,
                 f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg',
                 json.dumps(tags)))
        conn.commit()
    finally:
        conn.close()
    return db_path


def _seasons(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return {row['video_id']: (row['season'], row['season_confidence'],
                                  row['season_source'])
                for row in conn.execute(
                    'SELECT video_id, season, season_confidence, '
                    'season_source FROM videos')}
    finally:
        conn.close()


def test_derive_writes_high_confidence_only(derive_module, season_db, tmp_path):
    result = derive_module.derive(
        str(season_db), json_path=str(tmp_path / 'candidates.json'),
        verbose=False, decisions_path=str(tmp_path / 'decisions.json'))

    seasons = _seasons(season_db)
    assert seasons['vid_winter'] == ('winter', 'high', 'title:winter')
    assert seasons['vid_spring'] == ('spring', 'high', 'title:spring')
    # Unknown is a legitimate value: conflicted, evidence-free and
    # boilerplate-tagged videos are all left alone.
    assert seasons['vid_conflict'][0] is None
    assert seasons['vid_unknown'][0] is None
    assert seasons['vid_tagonly'][0] is None
    assert result['written_total'] == 2
    assert result['unknown'] == 3


def test_derive_is_idempotent(derive_module, season_db, tmp_path):
    kwargs = dict(json_path=str(tmp_path / 'candidates.json'), verbose=False,
                  decisions_path=str(tmp_path / 'decisions.json'))
    first = derive_module.derive(str(season_db), **kwargs)
    before = _seasons(season_db)
    second = derive_module.derive(str(season_db), **kwargs)

    assert first['written_total'] == 2
    assert second['written_total'] == 0, 'a second run must write nothing'
    assert _seasons(season_db) == before


def test_derive_never_overwrites_a_human_value(derive_module, season_db,
                                               tmp_path):
    conn = sqlite3.connect(season_db)
    conn.execute(
        "UPDATE videos SET season = 'summer', season_confidence = 'human', "
        "season_source = 'human:web-review' WHERE video_id = 'vid_winter'")
    conn.commit()
    conn.close()

    derive_module.derive(str(season_db),
                         json_path=str(tmp_path / 'candidates.json'),
                         verbose=False,
                         decisions_path=str(tmp_path / 'decisions.json'))

    # The title screams winter; the human said summer. The human wins.
    assert _seasons(season_db)['vid_winter'] == (
        'summer', 'human', 'human:web-review')


def test_derive_leaves_an_existing_value_alone(derive_module, season_db,
                                               tmp_path):
    """High-confidence values are only re-derived when the season is NULL."""
    conn = sqlite3.connect(season_db)
    conn.execute("UPDATE videos SET season = 'fall', season_confidence = "
                 "'high', season_source = 'title:fall' "
                 "WHERE video_id = 'vid_winter'")
    conn.commit()
    conn.close()

    result = derive_module.derive(
        str(season_db), json_path=str(tmp_path / 'candidates.json'),
        verbose=False, decisions_path=str(tmp_path / 'decisions.json'))

    assert _seasons(season_db)['vid_winter'][0] == 'fall'
    assert result['skipped_existing'] == 1


def test_derive_dumps_review_candidates(derive_module, season_db, tmp_path):
    json_path = tmp_path / 'candidates.json'
    derive_module.derive(str(season_db), json_path=str(json_path),
                         verbose=False,
                         decisions_path=str(tmp_path / 'decisions.json'))

    payload = json.loads(json_path.read_text())
    proposed = {(c['video_id'], c['proposed_season'])
                for c in payload['candidates']}
    assert ('vid_conflict', 'winter') in proposed
    assert ('vid_conflict', 'spring') in proposed
    assert ('vid_tagonly', 'winter') in proposed
    assert not any(c['video_id'] == 'vid_unknown'
                   for c in payload['candidates'])
    assert all(c['evidence'] for c in payload['candidates'])


def test_derive_skips_already_decided_videos(derive_module, season_db, tmp_path):
    decisions_path = tmp_path / 'decisions.json'
    decisions_path.write_text(json.dumps({'decisions': {
        'vid_conflict': {'video_id': 'vid_conflict', 'season': 'spring',
                         'decision': 'reject'},
        'vid_tagonly': {'video_id': 'vid_tagonly', 'season': 'winter',
                        'decision': 'reject'},
    }}))

    result = derive_module.derive(
        str(season_db), json_path=str(tmp_path / 'candidates.json'),
        verbose=False, decisions_path=str(decisions_path))

    assert result['review_candidates'] == 0
    assert result['already_decided_skipped'] == 3


def test_dry_run_writes_nothing(derive_module, season_db, tmp_path):
    json_path = tmp_path / 'candidates.json'
    derive_module.derive(str(season_db), json_path=str(json_path),
                         dry_run=True, verbose=False,
                         decisions_path=str(tmp_path / 'decisions.json'))
    assert all(value[0] is None for value in _seasons(season_db).values())
    assert not json_path.exists()


# ---------------------------------------------------------------------------
# review queue + site surfacing (Flask)
# ---------------------------------------------------------------------------

def _write_season_candidates(data_dir, db_path):
    payload = {
        'generated_at': '2026-08-21T00:00:00',
        'database': str(db_path),
        'count': 3,
        'note': 'test fixture',
        'candidates': [
            {'video_id': 'vid_conflict', 'title': 'Spring Snowstorm In A Hot Tent',
             'upload_date': '2024-04-01', 'proposed_season': 'spring',
             'rule': 'conflict:title:spring', 'evidence': 'Spring Snowstorm',
             'confidence': 'medium'},
            {'video_id': 'vid_tagonly', 'title': 'Overnight Camping With My Dogs',
             'upload_date': '2024-03-01', 'proposed_season': 'winter',
             'rule': 'tag:winter camping', 'evidence': 'youtube tag',
             'confidence': 'medium'},
            # Already has a high-confidence season -> must not be offered.
            {'video_id': 'vid_winter', 'title': 'Winter Camping In A Hot Tent',
             'upload_date': '2024-02-01', 'proposed_season': 'fall',
             'rule': 'description:fall', 'evidence': 'leaves',
             'confidence': 'medium'},
            # Not a season -> must be ignored outright.
            {'video_id': 'vid_unknown', 'title': '7 Night Canoe Adventure',
             'upload_date': '2024-07-01', 'proposed_season': 'monsoon',
             'rule': 'made-up', 'evidence': 'nonsense', 'confidence': 'medium'},
        ],
    }
    path = Path(data_dir) / 'season_review_candidates.json'
    path.write_text(json.dumps(payload, indent=2))
    return path


@pytest.fixture(scope='module')
def season_env(tmp_path_factory):
    scratch = tmp_path_factory.mktemp('posa_season_app_db')
    db_path = _run_create_database(scratch)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        _apply_migrations(conn)
        videos = [
            ('vid_winter', 'Winter Camping In A Hot Tent', '2024-02-01',
             'winter', 'high', 'title:winter'),
            ('vid_spring', 'Spring Canoe Camping With The Dogs', '2024-05-01',
             'spring', 'high', 'title:spring'),
            ('vid_conflict', 'Spring Snowstorm In A Hot Tent', '2024-04-01',
             None, None, None),
            ('vid_tagonly', 'Overnight Camping With My Dogs', '2024-03-01',
             None, None, None),
            ('vid_unknown', '7 Night Canoe Adventure [Full Trip]', '2024-07-01',
             None, None, None),
        ]
        for video_id, title, date, season, conf, source in videos:
            conn.execute(
                'INSERT INTO videos (video_id, title, upload_date, '
                'thumbnail_url, youtube_tags, season, season_confidence, '
                'season_source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (video_id, title, date,
                 f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg',
                 json.dumps([]), season, conf, source))
        from models.user import User
        User.create(ADMIN_USERNAME, 'season-admin@test.local', ADMIN_PASSWORD,
                    role='admin', db_conn=conn)
        conn.commit()
    finally:
        conn.close()

    data_dir = tmp_path_factory.mktemp('posa_season_data')
    _write_season_candidates(data_dir, db_path)

    return {'db_path': str(db_path), 'data_dir': str(data_dir)}


@pytest.fixture(scope='module')
def season_app(season_env):
    os.environ['DATABASE_PATH'] = season_env['db_path']
    os.environ['DATA_DIR'] = season_env['data_dir']
    os.environ['POSA_WIKI_ENV'] = 'testing'
    os.environ['RATELIMIT_ENABLED'] = 'false'

    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])
    if 'app' in sys.modules:
        app_module = importlib.reload(sys.modules['app'])
    else:
        app_module = importlib.import_module('app')

    flask_app = app_module.app
    assert flask_app.config['DATABASE_PATH'] == season_env['db_path']
    flask_app.config['WTF_CSRF_ENABLED'] = False

    yield flask_app

    for key in ('DATA_DIR', 'RATELIMIT_ENABLED'):
        os.environ.pop(key, None)
    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])


@pytest.fixture(scope='module')
def season_client(season_app):
    client = season_app.test_client()
    response = client.post('/auth/login', data={
        'username': ADMIN_USERNAME, 'password': ADMIN_PASSWORD,
    }, follow_redirects=True)
    assert response.status_code == 200
    return client


@pytest.fixture()
def anon(season_app):
    return season_app.test_client()


def _db(app):
    conn = sqlite3.connect(app.config['DATABASE_PATH'])
    conn.row_factory = sqlite3.Row
    return conn


# -- queue ------------------------------------------------------------------

def test_seasons_queue_is_registered():
    from services.review_service import QUEUES
    assert 'seasons' in QUEUES


def test_dashboard_counts_the_season_queue(season_client):
    body = season_client.get('/admin/').get_data(as_text=True)
    assert 'Season candidates' in body


def test_season_queue_lists_only_actionable_candidates(season_client):
    response = season_client.get('/admin/review/seasons')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Spring Snowstorm In A Hot Tent' in body   # conflicted, still NULL
    assert 'Overnight Camping With My Dogs' in body   # boilerplate tag
    # Already carries a high-confidence season -> not up for review.
    assert 'Winter Camping In A Hot Tent' not in body
    # 'monsoon' is not a season.
    assert '7 Night Canoe Adventure' not in body


def test_season_queue_shows_evidence(season_client):
    body = season_client.get('/admin/review/seasons').get_data(as_text=True)
    assert 'youtube tag' in body
    assert 'tag:winter camping' in body


def test_approve_writes_a_human_value(season_app, season_client, season_env):
    response = season_client.post(
        '/admin/review/seasons/approve',
        data={'payload': json.dumps({'video_id': 'vid_conflict',
                                     'season': 'spring'})},
        follow_redirects=True)
    assert response.status_code == 200

    conn = _db(season_app)
    try:
        row = conn.execute(
            'SELECT season, season_confidence, season_source FROM videos '
            "WHERE video_id = 'vid_conflict'").fetchone()
    finally:
        conn.close()
    assert row['season'] == 'spring'
    assert row['season_confidence'] == 'human'
    assert row['season_source'] == 'human:web-review'

    decisions = json.loads(
        (Path(season_env['data_dir']) / 'season_review_decisions.json')
        .read_text())['decisions']
    assert decisions['vid_conflict']['decision'] == 'approve'

    # ...and the card is gone.
    body = season_client.get('/admin/review/seasons').get_data(as_text=True)
    assert 'Spring Snowstorm In A Hot Tent' not in body


def test_reject_records_the_decision_without_touching_the_video(
        season_app, season_client, season_env):
    response = season_client.post(
        '/admin/review/seasons/reject',
        data={'payload': json.dumps({'video_id': 'vid_tagonly',
                                     'season': 'winter'})},
        follow_redirects=True)
    assert response.status_code == 200

    conn = _db(season_app)
    try:
        row = conn.execute(
            'SELECT season, season_confidence FROM videos '
            "WHERE video_id = 'vid_tagonly'").fetchone()
    finally:
        conn.close()
    # Rejecting means "Unknown stands".
    assert row['season'] is None
    assert row['season_confidence'] is None

    decisions = json.loads(
        (Path(season_env['data_dir']) / 'season_review_decisions.json')
        .read_text())['decisions']
    assert decisions['vid_tagonly']['decision'] == 'reject'

    body = season_client.get('/admin/review/seasons').get_data(as_text=True)
    assert 'Overnight Camping With My Dogs' not in body


def test_approving_a_bogus_season_is_refused(season_app):
    from services.review_service import SeasonCandidateQueue
    conn = _db(season_app)
    try:
        with pytest.raises(ValueError):
            SeasonCandidateQueue().approve(
                conn, {'video_id': 'vid_unknown', 'season': 'monsoon'})
    finally:
        conn.close()


def test_queue_requires_login(anon):
    response = anon.get('/admin/review/seasons')
    assert response.status_code == 302
    assert '/auth/login' in response.headers['Location']


# -- site surfacing ---------------------------------------------------------

def test_videos_season_filter(anon):
    body = anon.get('/videos?season=winter').get_data(as_text=True)
    assert 'Winter Camping In A Hot Tent' in body
    assert 'Spring Canoe Camping With The Dogs' not in body


def test_videos_unknown_filter_selects_nulls(anon):
    body = anon.get('/videos?season=unknown').get_data(as_text=True)
    assert '7 Night Canoe Adventure' in body
    assert 'Winter Camping In A Hot Tent' not in body


def test_videos_unfiltered_shows_everything(anon):
    body = anon.get('/videos').get_data(as_text=True)
    assert 'Winter Camping In A Hot Tent' in body
    assert '7 Night Canoe Adventure' in body


def test_videos_bogus_season_is_ignored(anon):
    response = anon.get('/videos?season=monsoon')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Winter Camping In A Hot Tent' in body
    assert '7 Night Canoe Adventure' in body


def test_season_chip_row_renders_with_counts(anon):
    body = anon.get('/videos').get_data(as_text=True)
    assert 'season-filter' in body
    for label in ('❄️ Winter', '🌱 Spring', '☀️ Summer', '🍂 Fall',
                  '❔ Unknown'):
        assert label in body


def test_season_filter_preserves_sort_params(anon):
    body = anon.get('/videos?sort=title&order=asc').get_data(as_text=True)
    assert 'sort=title' in body and 'order=asc' in body
    assert 'season=winter' in body


def test_detail_page_renders_the_season_badge(anon):
    body = anon.get('/video/vid_winter').get_data(as_text=True)
    assert 'season-chip' in body
    assert '❄️ Winter' in body


def test_detail_page_omits_the_badge_when_unknown(anon):
    body = anon.get('/video/vid_unknown').get_data(as_text=True)
    assert 'season-chip' not in body


def test_watch_page_renders_the_season_badge(anon):
    body = anon.get('/watch/vid_spring').get_data(as_text=True)
    assert '🌱 Spring' in body

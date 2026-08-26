"""Tests for the /admin review-queue UI (Phase 2B Step 2).

Builds its own throwaway database (so the shared session fixtures in
conftest.py stay untouched) plus a scratch ``DATA_DIR`` / tag-authority file,
then drives the queues end to end: dashboard, each queue page, approve, reject,
and the "decisions stick" behaviour.
"""

import importlib
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.conftest import _apply_migrations, _run_create_database  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

ADMIN_USERNAME = 'review-admin'
ADMIN_PASSWORD = 'review-password'

TAG_AUTHORITY_SEED = {
    'authorities': [
        {
            'canonical_name': 'Dogs',
            'category': 'subject',
            'aliases': ['dog', 'dogs'],
            'description': 'Content featuring dogs',
        }
    ],
    'analysis': {'total_authorities': 1, 'total_aliases': 2},
}


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _seed_review_rows(conn):
    """Videos for each queue: a series candidate, a tag, a Lucas video."""
    videos = [
        ('vid_hike', 'A Beautiful Fall Hike With My Dogs', '2024-04-02',
         json.dumps(['gopro', 'dogs']), json.dumps(['Dogs']),
         json.dumps(['gopro'])),
        ('vid_lucas', 'Camping With Lucas', '2024-05-11',
         json.dumps(['gopro']), json.dumps([]), json.dumps(['gopro'])),
        ('vid_plain', 'Just A Quiet Paddle', '2024-06-01',
         json.dumps(['pulk']), json.dumps([]), json.dumps(['pulk'])),
    ]
    for video_id, title, upload_date, yt, val, unval in videos:
        conn.execute(
            'INSERT INTO videos (video_id, title, upload_date, thumbnail_url, '
            'youtube_tags, validated_tags, unvalidated_tags) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (video_id, title, upload_date,
             f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg', yt, val, unval),
        )

    # 'Day Hiking' is added by scripts/seed_series.py, not by
    # create_database.py, so the fixture database needs it explicitly.
    conn.execute(
        "INSERT INTO series (name, description, is_episodic, series_type) "
        "VALUES ('Day Hiking', 'Day hikes', 0, 'activity')")

    # Lucas (person 3) is in vid_lucas; Layla (dog 3) is not -> Layla rule.
    conn.execute(
        'INSERT INTO video_people (video_id, person_id, role) VALUES (?, ?, ?)',
        ('vid_lucas', 3, 'guest'),
    )
    conn.commit()


def _write_candidates(data_dir, db_path):
    """A candidates dump: one live series, one retired, one nonexistent."""
    payload = {
        'generated_at': '2026-08-20T00:00:00',
        'database': str(db_path),
        'count': 3,
        'note': 'test fixture',
        'candidates': [
            {'video_id': 'vid_hike', 'title': 'A Beautiful Fall Hike With My Dogs',
             'upload_date': '2024-04-02', 'proposed_series': 'Day Hiking',
             'rule': 'title-hike-without-overnight', 'confidence': 'medium'},
            {'video_id': 'vid_lucas', 'title': 'Camping With Lucas',
             'upload_date': '2024-05-11', 'proposed_series': 'Michigan Adventures',
             'rule': 'michigan-in-title', 'confidence': 'medium'},
            {'video_id': 'vid_plain', 'title': 'Just A Quiet Paddle',
             'upload_date': '2024-06-01', 'proposed_series': 'Nonexistent Series',
             'rule': 'made-up', 'confidence': 'medium'},
        ],
    }
    path = Path(data_dir) / 'series_review_candidates.json'
    path.write_text(json.dumps(payload, indent=2))
    return path


@pytest.fixture(scope='module')
def review_env(tmp_path_factory):
    """Throwaway db + scratch data dir + tag authority file."""
    scratch = tmp_path_factory.mktemp('posa_review_db')
    db_path = _run_create_database(scratch)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        _apply_migrations(conn)
        _seed_review_rows(conn)
        from models.user import User
        User.create(ADMIN_USERNAME, 'review-admin@test.local', ADMIN_PASSWORD,
                    role='admin', db_conn=conn)
        User.create('review-viewer', 'review-viewer@test.local', ADMIN_PASSWORD,
                    role='viewer', db_conn=conn)
    finally:
        conn.close()

    data_dir = tmp_path_factory.mktemp('posa_review_data')
    _write_candidates(data_dir, db_path)

    authority_path = Path(data_dir) / 'tag_authority_system.json'
    authority_path.write_text(json.dumps(TAG_AUTHORITY_SEED, indent=2))

    return {
        'db_path': str(db_path),
        'data_dir': str(data_dir),
        'authority_path': str(authority_path),
    }


@pytest.fixture(scope='module')
def admin_app(review_env):
    """Reimport the Flask app pointed at the review fixtures."""
    os.environ['DATABASE_PATH'] = review_env['db_path']
    os.environ['DATA_DIR'] = review_env['data_dir']
    os.environ['TAG_AUTHORITY_PATH'] = review_env['authority_path']
    os.environ['POSA_WIKI_ENV'] = 'testing'
    # The login route is throttled to 5/minute; this module logs in repeatedly.
    os.environ['RATELIMIT_ENABLED'] = 'false'

    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])
    if 'app' in sys.modules:
        app_module = importlib.reload(sys.modules['app'])
    else:
        app_module = importlib.import_module('app')

    flask_app = app_module.app
    assert flask_app.config['DATABASE_PATH'] == review_env['db_path']
    flask_app.config['WTF_CSRF_ENABLED'] = False

    yield flask_app

    # Leave the environment clean for the session-scoped fixtures in
    # conftest.py, which reload the app module against their own database.
    for key in ('DATA_DIR', 'TAG_AUTHORITY_PATH', 'RATELIMIT_ENABLED'):
        os.environ.pop(key, None)
    if 'config' in sys.modules:
        importlib.reload(sys.modules['config'])


@pytest.fixture()
def anon_client(admin_app):
    return admin_app.test_client()


@pytest.fixture(scope='module')
def client(admin_app):
    """A client logged in as an admin user (shared across the module)."""
    test_client = admin_app.test_client()
    response = test_client.post('/auth/login', data={
        'username': ADMIN_USERNAME,
        'password': ADMIN_PASSWORD,
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Invalid username or password' not in response.data
    return test_client


@pytest.fixture()
def audit_records():
    """Capture everything create_audit_log() enqueues.

    The SQLite audit handler is asynchronous and bound to whichever database
    initialised it first in the process, so assert on the 'audit' logger
    itself -- that is the actual call site create_audit_log() writes through.
    """
    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture()
    logger = logging.getLogger('audit')
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)


def _db(admin_app):
    conn = sqlite3.connect(admin_app.config['DATABASE_PATH'])
    conn.row_factory = sqlite3.Row
    return conn


def _read_json(path):
    with open(path, 'r', encoding='utf-8') as handle:
        return json.load(handle)


def _payload(**kwargs):
    return json.dumps(kwargs, sort_keys=True)


# ---------------------------------------------------------------------------
# access control
# ---------------------------------------------------------------------------

def test_admin_requires_login(anon_client):
    response = anon_client.get('/admin/')
    assert response.status_code == 302
    assert '/auth/login' in response.headers['Location']


def test_queue_requires_login(anon_client):
    response = anon_client.get('/admin/review/series')
    assert response.status_code == 302
    assert '/auth/login' in response.headers['Location']


def test_viewer_is_forbidden(admin_app):
    viewer = admin_app.test_client()
    viewer.post('/auth/login', data={'username': 'review-viewer',
                                     'password': ADMIN_PASSWORD},
                follow_redirects=True)
    response = viewer.get('/admin/')
    assert response.status_code == 403


def test_unknown_queue_404s(client):
    assert client.get('/admin/review/nope').status_code == 404


def test_post_without_csrf_token_is_rejected(admin_app, client):
    admin_app.config['WTF_CSRF_ENABLED'] = True
    try:
        response = client.post('/admin/review/dogs/approve',
                               data={'payload': _payload(video_id='vid_lucas')})
        assert response.status_code == 400
    finally:
        admin_app.config['WTF_CSRF_ENABLED'] = False


# ---------------------------------------------------------------------------
# dashboard + queue pages
# ---------------------------------------------------------------------------

def test_dashboard_renders_with_counts(client):
    response = client.get('/admin/')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Series candidates' in body
    assert 'Unvalidated tags' in body
    assert 'Dog candidates' in body
    assert 'Catalogue stats' in body


def test_admin_link_in_sidebar_for_editor(client, anon_client):
    assert 'Admin &amp; Review' in client.get('/').get_data(as_text=True)
    assert 'Admin &amp; Review' not in anon_client.get('/').get_data(as_text=True)


def test_series_queue_hides_retired_and_unknown_series(client):
    response = client.get('/admin/review/series')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Day Hiking' in body
    assert 'Michigan Adventures' not in body   # retired by owner decision
    assert 'Nonexistent Series' not in body    # not in this database


def test_tag_queue_lists_distinct_tags_with_counts(client):
    response = client.get('/admin/review/tags')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'gopro' in body           # on two videos
    assert 'pulk' in body
    assert '2 videos' in body


def test_dog_queue_lists_lucas_video(client):
    response = client.get('/admin/review/dogs')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Camping With Lucas' in body
    assert 'Layla may appear' in body


# ---------------------------------------------------------------------------
# series queue actions
# ---------------------------------------------------------------------------

def test_series_approve_writes_row_and_decision(admin_app, client, review_env,
                                                audit_records):
    response = client.post(
        '/admin/review/series/approve',
        data={'payload': _payload(video_id='vid_hike', series='Day Hiking')},
        follow_redirects=True)
    assert response.status_code == 200

    conn = _db(admin_app)
    try:
        row = conn.execute(
            'SELECT vs.notes FROM video_series vs JOIN series s '
            'ON s.series_id = vs.series_id '
            'WHERE vs.video_id = ? AND s.name = ?',
            ('vid_hike', 'Day Hiking')).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row['notes'] == 'human:web-review'

    decisions = _read_json(
        Path(review_env['data_dir']) / 'series_review_decisions.json')
    assert decisions['decisions']['vid_hike|Day Hiking']['decision'] == 'approve'

    # ...and it is gone from the queue on the next GET.
    body = client.get('/admin/review/series').get_data(as_text=True)
    assert 'A Beautiful Fall Hike With My Dogs' not in body

    events = [getattr(r, 'event_type', None) for r in audit_records]
    assert 'review.series.approve' in events


def test_series_reject_only_writes_decision(admin_app, client, review_env,
                                            audit_records):
    # Re-open the candidate by rewriting the dump (assign_series.py would).
    _write_candidates(review_env['data_dir'], review_env['db_path'])

    response = client.post(
        '/admin/review/series/reject',
        data={'payload': _payload(video_id='vid_plain', series='Day Hiking')},
        follow_redirects=True)
    assert response.status_code == 200

    conn = _db(admin_app)
    try:
        row = conn.execute(
            'SELECT 1 FROM video_series WHERE video_id = ?',
            ('vid_plain',)).fetchone()
    finally:
        conn.close()
    assert row is None

    decisions = _read_json(
        Path(review_env['data_dir']) / 'series_review_decisions.json')
    assert decisions['decisions']['vid_plain|Day Hiking']['decision'] == 'reject'
    assert 'review.series.reject' in [getattr(r, 'event_type', None)
                                      for r in audit_records]


def test_assign_series_skips_decided_pairs(review_env):
    """scripts/assign_series.py reads the same decisions file."""
    import scripts.assign_series as assign_series

    decisions_path = (Path(review_env['data_dir'])
                      / 'series_review_decisions.json')
    assert decisions_path.exists()
    decisions = assign_series.load_series_decisions(decisions_path)
    assert assign_series.series_decision_key('vid_hike', 'Day Hiking') in decisions


# ---------------------------------------------------------------------------
# tag queue actions
# ---------------------------------------------------------------------------

def test_tag_approve_creates_authority_and_revalidates(admin_app, client,
                                                       review_env,
                                                       audit_records):
    response = client.post('/admin/review/tags/approve',
                           data={'payload': _payload(tag='gopro')},
                           follow_redirects=True)
    assert response.status_code == 200

    authority = _read_json(review_env['authority_path'])
    canonical = [a['canonical_name'] for a in authority['authorities']]
    assert 'Gopro' in canonical
    promoted = next(a for a in authority['authorities']
                    if a['canonical_name'] == 'Gopro')
    assert 'gopro' in promoted['aliases']

    conn = _db(admin_app)
    try:
        row = conn.execute(
            'SELECT validated_tags, unvalidated_tags FROM videos '
            'WHERE video_id = ?', ('vid_hike',)).fetchone()
    finally:
        conn.close()
    assert 'Gopro' in json.loads(row['validated_tags'])
    assert 'gopro' not in json.loads(row['unvalidated_tags'])

    body = client.get('/admin/review/tags').get_data(as_text=True)
    assert 'gopro' not in body
    assert 'review.tags.approve' in [getattr(r, 'event_type', None)
                                     for r in audit_records]


def test_tag_reject_persists_dismissal(client, review_env, audit_records):
    response = client.post('/admin/review/tags/reject',
                           data={'payload': _payload(tag='pulk')},
                           follow_redirects=True)
    assert response.status_code == 200

    dismissed = _read_json(
        Path(review_env['data_dir']) / 'tag_review_dismissed.json')
    assert 'pulk' in dismissed['dismissed']

    body = client.get('/admin/review/tags').get_data(as_text=True)
    assert 'pulk' not in body
    assert 'review.tags.reject' in [getattr(r, 'event_type', None)
                                    for r in audit_records]


# ---------------------------------------------------------------------------
# dog queue actions
# ---------------------------------------------------------------------------

def test_dog_approve_links_layla_with_provenance(admin_app, client,
                                                 audit_records):
    response = client.post('/admin/review/dogs/approve',
                           data={'payload': _payload(video_id='vid_lucas')},
                           follow_redirects=True)
    assert response.status_code == 200

    conn = _db(admin_app)
    try:
        row = conn.execute(
            'SELECT vd.notes FROM video_dogs vd JOIN dogs d '
            'ON d.dog_id = vd.dog_id '
            'WHERE vd.video_id = ? AND d.name = ?',
            ('vid_lucas', 'Layla')).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row['notes'].startswith('human:web-review')

    body = client.get('/admin/review/dogs').get_data(as_text=True)
    assert 'Camping With Lucas' not in body
    assert 'review.dogs.approve' in [getattr(r, 'event_type', None)
                                     for r in audit_records]


def test_dog_approve_rejects_video_without_lucas(client):
    response = client.post('/admin/review/dogs/approve',
                           data={'payload': _payload(video_id='vid_plain')},
                           follow_redirects=True)
    assert response.status_code == 200
    assert 'Lucas is not linked' in response.get_data(as_text=True)


def test_dog_reject_persists_dismissal(admin_app, client, review_env):
    conn = _db(admin_app)
    try:
        conn.execute(
            'INSERT INTO video_people (video_id, person_id, role) '
            'VALUES (?, ?, ?)', ('vid_plain', 3, 'guest'))
        conn.commit()
    finally:
        conn.close()

    assert 'Just A Quiet Paddle' in client.get(
        '/admin/review/dogs').get_data(as_text=True)

    client.post('/admin/review/dogs/reject',
                data={'payload': _payload(video_id='vid_plain')},
                follow_redirects=True)

    dismissed = _read_json(
        Path(review_env['data_dir']) / 'dog_review_dismissed.json')
    assert 'vid_plain' in dismissed['dismissed']
    assert 'Just A Quiet Paddle' not in client.get(
        '/admin/review/dogs').get_data(as_text=True)


# ---------------------------------------------------------------------------
# bulk action
# ---------------------------------------------------------------------------

def test_bulk_approve_applies_every_payload(admin_app, client, review_env):
    conn = _db(admin_app)
    try:
        conn.execute(
            "INSERT INTO videos (video_id, title, upload_date, youtube_tags, "
            "validated_tags, unvalidated_tags) VALUES "
            "('vid_bulk_a', 'Bulk One', '2024-07-01', '[]', '[]', '[]')")
        conn.execute(
            "INSERT INTO videos (video_id, title, upload_date, youtube_tags, "
            "validated_tags, unvalidated_tags) VALUES "
            "('vid_bulk_b', 'Bulk Two', '2024-07-02', '[]', '[]', '[]')")
        conn.commit()
    finally:
        conn.close()

    response = client.post('/admin/review/series/approve', data={
        'payload': [_payload(video_id='vid_bulk_a', series='Day Hiking'),
                    _payload(video_id='vid_bulk_b', series='Day Hiking')],
    }, follow_redirects=True)
    assert response.status_code == 200

    conn = _db(admin_app)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM video_series WHERE video_id IN "
            "('vid_bulk_a', 'vid_bulk_b') AND notes = 'human:web-review'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 2


# ---------------------------------------------------------------------------
# transcripts queue (migration 013)
# ---------------------------------------------------------------------------

def _seed_transcript_span(admin_app, item_id, proposed=None):
    """One Whisper segment plus an open review row pointing at it."""
    conn = _db(admin_app)
    try:
        conn.execute(
            'INSERT INTO transcript_segments '
            '(video_id, start_seconds, duration_seconds, text, source) '
            "VALUES ('vid_lucas', 12.0, 3.0, "
            "'Captain Tea Truck caught seven of them.', 'whisper-large-v3')")
        conn.execute(
            'INSERT INTO transcript_review_queue '
            '(item_id, video_id, start_seconds, end_seconds, draft_sentence, '
            ' witness_disagreement, judge_reasoning, proposed_correction, '
            " status, created_at) VALUES (?, 'vid_lucas', 12.0, 15.0, "
            "'Captain Tea Truck caught seven of them.', "
            '\'draft "tea truck" vs youtube heard "trot"\', '
            "'roster alias', ?, 'open', '2026-08-25T00:00:00')",
            (item_id, proposed))
        conn.commit()
    finally:
        conn.close()


def test_transcripts_queue_page_renders(admin_app, client):
    _seed_transcript_span(admin_app, 'vid_lucas:render',
                          'Captain Teeny Trout caught seven of them.')
    response = client.get('/admin/review/transcripts')
    assert response.status_code == 200
    assert b'Captain Teeny Trout caught seven of them.' in response.data
    assert b'Camping With Lucas' in response.data


def test_transcripts_queue_appears_on_the_dashboard(admin_app, client):
    _seed_transcript_span(admin_app, 'vid_lucas:dashboard')
    response = client.get('/admin/')
    assert response.status_code == 200
    assert b'Transcript spans' in response.data


def test_transcripts_approve_applies_and_logs(admin_app, client):
    _seed_transcript_span(admin_app, 'vid_lucas:approve',
                          'Captain Teeny Trout caught seven of them.')
    response = client.post('/admin/review/transcripts/approve', data={
        'payload': _payload(item_id='vid_lucas:approve'),
    }, follow_redirects=True)
    assert response.status_code == 200

    conn = _db(admin_app)
    try:
        row = conn.execute(
            'SELECT status, decision_note FROM transcript_review_queue '
            "WHERE item_id = 'vid_lucas:approve'").fetchone()
        assert row['status'] == 'approved'
        texts = [r['text'] for r in conn.execute(
            "SELECT text FROM transcript_segments WHERE video_id = 'vid_lucas' "
            "AND source = 'whisper-large-v3'")]
        assert 'Captain Teeny Trout caught seven of them.' in texts
        logged = conn.execute(
            'SELECT provenance FROM transcript_corrections '
            "WHERE video_id = 'vid_lucas'").fetchall()
        assert any(r['provenance'] == 'human:web-review' for r in logged)
    finally:
        conn.close()


def test_transcripts_reject_keeps_the_draft(admin_app, client):
    _seed_transcript_span(admin_app, 'vid_lucas:reject',
                          'Captain Teeny Trout caught seven of them.')
    response = client.post('/admin/review/transcripts/reject', data={
        'payload': _payload(item_id='vid_lucas:reject'),
    }, follow_redirects=True)
    assert response.status_code == 200

    conn = _db(admin_app)
    try:
        row = conn.execute(
            'SELECT status FROM transcript_review_queue '
            "WHERE item_id = 'vid_lucas:reject'").fetchone()
        assert row['status'] == 'rejected'
    finally:
        conn.close()

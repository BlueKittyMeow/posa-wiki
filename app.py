#!/usr/bin/env python3
"""
Posa Wiki - Flask Web Interface
Dark hacker girl aesthetic with fairyfloss theme and rounded edges
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, abort
from flask_paginate import Pagination, get_page_args
from flask_login import LoginManager, current_user
from flask_wtf import CSRFProtect
from flask_jwt_extended import JWTManager
from werkzeug.middleware.proxy_fix import ProxyFix
from markupsafe import Markup, escape
import json
import sqlite3
from datetime import datetime, timedelta
import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import db as db_module
from db import get_db
from config import CONFIG_BY_NAME, Config
from models.user import User
from utils.duration import format_seconds, parse_duration_to_seconds
from services.auth_service import init_jwt_redis, is_token_revoked
from services.audit_log_service import init_audit_logging, create_audit_log
from services.rate_limit_service import init_rate_limiter

def from_json(value):
    """Template filter to parse JSON strings"""
    if value and value != 'null':
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    return []

def format_duration(value):
    """Template filter: render a duration as H:MM:SS or M:SS.

    Prefers an integer seconds value (videos.duration_seconds), but falls back
    gracefully when handed the legacy string form ('9:31', 'PT9M31S') so any
    template still passing `video.duration` keeps working.
    """
    if value is None or value == '':
        return "Unknown"

    seconds = parse_duration_to_seconds(value)
    if seconds is None:
        # Unparseable - show whatever we were given rather than losing it.
        return str(value)

    return format_seconds(seconds)


def configure_logging(app):
    """Attach logging handlers tailored to the environment."""
    logging.basicConfig(level=logging.INFO)
    app.logger.setLevel(logging.INFO)

    if app.debug or app.testing:
        return

    logs_dir = Path('logs')
    logs_dir.mkdir(exist_ok=True)

    log_path = logs_dir / 'posa_wiki.log'
    file_handler = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=5)
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    if not any(isinstance(handler, RotatingFileHandler) for handler in app.logger.handlers):
        app.logger.addHandler(file_handler)


env_name = os.getenv('POSA_WIKI_ENV', os.getenv('FLASK_ENV', 'development')).lower()
config_class = CONFIG_BY_NAME.get(env_name, Config)

app = Flask(__name__)
app.config.from_object(config_class)
config_class.init_app(app)
configure_logging(app)

# Behind cloudflared/nginx every request arrives from 127.0.0.1, which collapses
# per-IP rate limiting into a single bucket and hides the real client IP from
# the audit log. Enable with PROXY_FIX=1 *only* when a trusted proxy really is
# in front of the app -- otherwise clients could spoof X-Forwarded-For.
if os.getenv('PROXY_FIX') == '1':
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# Request-scoped DB connection + teardown (see db.py)
db_module.init_app(app)

init_rate_limiter(app)
init_audit_logging(app)

csrf = CSRFProtect()
csrf.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# Initialize JWT for API authentication
jwt = JWTManager(app)
init_jwt_redis(app)


@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    """Check if a JWT token has been revoked (logged out)"""
    return is_token_revoked(jwt_header, jwt_payload)


@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    """Handle expired tokens"""
    return jsonify({
        'error': 'token_expired',
        'message': 'The token has expired. Please refresh or log in again.'
    }), 401


@jwt.invalid_token_loader
def invalid_token_callback(error):
    """Handle invalid tokens"""
    return jsonify({
        'error': 'invalid_token',
        'message': 'Invalid token. Please log in again.'
    }), 401


@jwt.unauthorized_loader
def missing_token_callback(error):
    """Handle missing tokens"""
    return jsonify({
        'error': 'authorization_required',
        'message': 'API request requires authentication token.'
    }), 401


@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    """Handle revoked tokens (logged out)"""
    return jsonify({
        'error': 'token_revoked',
        'message': 'The token has been revoked. Please log in again.'
    }), 401


@login_manager.user_loader
def load_user(user_id):
    """Load user for Flask-Login session management"""
    conn = get_db()
    user = User.get_by_id(user_id, conn)
    return user


@app.context_processor
def inject_sidebar_data():
    """Inject data for the sidebar into all templates"""
    conn = get_db()

    sidebar_people = conn.execute('''
        SELECT p.person_id, p.canonical_name, COUNT(vp.video_id) as video_count
        FROM people p
        LEFT JOIN video_people vp ON p.person_id = vp.person_id
        GROUP BY p.person_id, p.canonical_name
        ORDER BY video_count DESC
        LIMIT 3
    ''').fetchall()

    sidebar_dogs = conn.execute('''
        SELECT d.dog_id, d.name, COUNT(vd.video_id) as video_count
        FROM dogs d
        LEFT JOIN video_dogs vd ON d.dog_id = vd.dog_id
        GROUP BY d.dog_id, d.name
        ORDER BY video_count DESC
        LIMIT 3
    ''').fetchall()

    # name -> series_id lookup so templates can link to featured series
    # without hardcoding ids (they differ between local and production dbs).
    series_ids = {
        row['name']: row['series_id']
        for row in conn.execute('SELECT series_id, name FROM series')
    }

    return dict(sidebar_people=sidebar_people, sidebar_dogs=sidebar_dogs,
                series_ids=series_ids)


# Register blueprints
from blueprints.auth import auth_bp
from blueprints.admin import admin_bp
from blueprints.crud import crud_bp
from blueprints.api import api_base_bp
from blueprints.api.v1 import api_v1_bp
from blueprints.api.v1.auth import auth_api_bp

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(crud_bp)
app.register_blueprint(api_base_bp)
app.register_blueprint(api_v1_bp)

csrf.exempt(auth_api_bp)

csrf.exempt(api_base_bp)
csrf.exempt(api_v1_bp)

csrf.exempt(api_base_bp)
csrf.exempt(api_v1_bp)


# Register template filters
app.jinja_env.filters['from_json'] = from_json
app.jinja_env.filters['format_duration'] = format_duration

# Add timedelta to template globals for date navigation
app.jinja_env.globals['timedelta'] = timedelta

# Cache-buster for static assets: production serves them with a 1-year
# max-age, so stamp URLs with the stylesheet's mtime — deploys change it.
try:
    STATIC_VERSION = int(os.path.getmtime(
        Path(app.static_folder) / 'css' / 'fairyfloss.css'))
except OSError:
    STATIC_VERSION = 1
app.jinja_env.globals['STATIC_V'] = STATIC_VERSION

# Season is a facet of a video, not a series. 'unknown' (season IS NULL) is a
# legitimate, first-class value -- most of the catalogue has no season
# evidence and we never guess one. Chip order matches the calendar.
SEASON_FILTERS = (
    ('winter', '❄️ Winter'),
    ('spring', '🌱 Spring'),
    ('summer', '☀️ Summer'),
    ('fall', '🍂 Fall'),
    ('unknown', '❔ Unknown'),
)
SEASON_FILTER_KEYS = frozenset(key for key, _label in SEASON_FILTERS)

# Trip length is the other video facet (migration 012). The buckets are the
# shapes of trip he actually films, not arithmetic slices; 'unknown'
# (number_of_nights IS NULL) is again first-class -- most of the catalogue has
# no stated length and we never guess one. ``None`` as the upper bound means
# open-ended; ``None`` as the whole range means "IS NULL".
NIGHTS_FILTERS = (
    ('day', '🥾 Day trip', (0, 0)),
    ('overnight', '🌙 Overnight', (1, 1)),
    ('weekend', '⛺ Weekend', (2, 3)),
    ('week', '🏕️ Week-ish', (4, 7)),
    ('epic', '🗺️ Epic', (8, None)),
    ('unknown', '❔ Unknown', None),
)
NIGHTS_FILTER_KEYS = frozenset(key for key, _label, _range in NIGHTS_FILTERS)
NIGHTS_FILTER_RANGES = {key: bounds for key, _label, bounds in NIGHTS_FILTERS}


def nights_bucket(nights):
    """Return the filter key for a concrete ``number_of_nights`` value."""
    if nights is None:
        return 'unknown'
    for key, _label, bounds in NIGHTS_FILTERS:
        if bounds is None:
            continue
        low, high = bounds
        if nights >= low and (high is None or nights <= high):
            return key
    return 'unknown'


def paginate(conn, query, params, count_query, count_params=(), per_page=20):
    """A helper function to paginate queries."""
    page, per_page, offset = get_page_args(page_parameter='page', 
                                           per_page_parameter='per_page', 
                                           default_per_page=per_page)
    
    total = conn.execute(count_query, count_params).fetchone()[0]
    
    paginated_query = query + " LIMIT ? OFFSET ?"
    results = conn.execute(paginated_query, params + (per_page, offset)).fetchall()
    
    pagination = Pagination(page=page, per_page=per_page, total=total,
                            css_framework='bootstrap4',
                            record_name='items')
    
    return results, pagination

@app.errorhandler(403)
def handle_forbidden(error):
    app.logger.warning('403 Forbidden: %s by user %s', request.path,
                      current_user.username if current_user.is_authenticated else 'anonymous')
    create_audit_log(
        event_type='access_denied',
        resource_type='url',
        resource_id=request.path,
        details={'message': str(error)}
    )
    return render_template('errors/403.html'), 403


@app.errorhandler(404)
def handle_not_found(error):
    app.logger.warning('404 Not Found: %s', request.path)
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def handle_server_error(error):
    app.logger.exception('500 Internal Server Error on %s', request.path)
    return render_template('errors/500.html'), 500


@app.route('/')
def index():
    """Landing page with date nav, search, and browse options"""
    conn = get_db()
    
    # Get recent videos (last 6)
    recent_videos = conn.execute('''
    SELECT video_id, title, description, upload_date, thumbnail_url
    FROM videos 
    ORDER BY upload_date DESC
    LIMIT 6
    ''').fetchall()
    
    # Get basic stats
    stats = {
        'total_videos': conn.execute('SELECT COUNT(*) FROM videos').fetchone()[0],
        'total_people': conn.execute('SELECT COUNT(*) FROM people').fetchone()[0],
        'total_dogs': conn.execute('SELECT COUNT(*) FROM dogs').fetchone()[0],
    }

    return render_template('index.html', recent_videos=recent_videos, stats=stats)

@app.route('/videos')
def video_list():
    """Sortable video list with thumbnails, optionally filtered by season"""
    sort_by = request.args.get('sort', 'upload_date')
    order = request.args.get('order', 'desc')

    # Season is a video facet. 'unknown' is a first-class choice (season IS
    # NULL) -- most of the catalogue genuinely has no season evidence, and
    # that is an answer, not a gap.
    season = (request.args.get('season') or '').lower()
    if season not in SEASON_FILTER_KEYS:
        season = ''

    # Trip length is the same kind of facet, and composes with the season.
    nights = (request.args.get('nights') or '').lower()
    if nights not in NIGHTS_FILTER_KEYS:
        nights = ''

    clauses, filter_params = [], []
    if season == 'unknown':
        clauses.append('season IS NULL')
    elif season:
        clauses.append('season = ?')
        filter_params.append(season)

    if nights == 'unknown':
        clauses.append('number_of_nights IS NULL')
    elif nights:
        low, high = NIGHTS_FILTER_RANGES[nights]
        if high is None:
            clauses.append('number_of_nights >= ?')
            filter_params.append(low)
        else:
            clauses.append('number_of_nights BETWEEN ? AND ?')
            filter_params.extend((low, high))

    filter_sql = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    filter_params = tuple(filter_params)

    conn = get_db()

    # Pagination
    page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page', default_per_page=20)

    # Get total number of videos for pagination
    total = conn.execute(
        f'SELECT COUNT(*) FROM videos {filter_sql}', filter_params).fetchone()[0]

    # Chip-row counts, so the filter shows how much is behind each option.
    season_counts = {row[0] or 'unknown': row[1] for row in conn.execute(
        'SELECT season, COUNT(*) FROM videos GROUP BY season')}
    season_counts['all'] = sum(season_counts.values())

    # Same for trip length, bucketed in Python so the buckets live in exactly
    # one place (NIGHTS_FILTERS) rather than being restated as SQL CASEs.
    nights_counts = {}
    for value, count in conn.execute(
            'SELECT number_of_nights, COUNT(*) FROM videos '
            'GROUP BY number_of_nights'):
        key = nights_bucket(value)
        nights_counts[key] = nights_counts.get(key, 0) + count
    nights_counts['all'] = sum(nights_counts.values())

    # Build SQL query with sorting and pagination
    order_sql = 'ASC' if order == 'asc' else 'DESC'
    # Map the public sort key to the column actually ordered on. 'duration' is
    # a display string ('9:31', '10:00:36') and sorts lexicographically, so
    # order by the numeric duration_seconds instead.
    sort_columns = {
        'upload_date': 'upload_date',
        'title': 'title',
        'duration': 'duration_seconds',
        'view_count': 'view_count',
    }
    if sort_by not in sort_columns:
        sort_by = 'upload_date'
    sort_column = sort_columns[sort_by]

    # Keep NULLs at the end regardless of direction.
    query = f'''
    SELECT video_id, title, description, upload_date, duration, duration_seconds,
           view_count, thumbnail_url, season, number_of_nights
    FROM videos
    {filter_sql}
    ORDER BY ({sort_column} IS NULL) ASC, {sort_column} {order_sql}
    LIMIT ? OFFSET ?
    '''

    videos = conn.execute(query, filter_params + (per_page, offset)).fetchall()

    pagination = Pagination(page=page, per_page=per_page, total=total,
                            css_framework='bootstrap4',
                            record_name='videos')

    return render_template('video_list.html',
                         videos=videos,
                         sort_by=sort_by,
                         order=order,
                         season=season,
                         season_filters=SEASON_FILTERS,
                         season_counts=season_counts,
                         nights=nights,
                         nights_filters=NIGHTS_FILTERS,
                         nights_counts=nights_counts,
                         pagination=pagination)

@app.route('/video/<video_id>')
def video_detail(video_id):
    """Video detail page with metadata and related videos"""
    conn = get_db()
    
    # Get video details
    video = conn.execute('''
    SELECT * FROM videos WHERE video_id = ?
    ''', (video_id,)).fetchone()
    
    if not video:
        abort(404)
    
    # Get associated people
    people = conn.execute('''
    SELECT p.person_id, p.canonical_name 
    FROM people p
    JOIN video_people vp ON p.person_id = vp.person_id
    WHERE vp.video_id = ?
    ''', (video_id,)).fetchall()
    
    # Get associated dogs
    dogs = conn.execute('''
    SELECT d.dog_id, d.name 
    FROM dogs d
    JOIN video_dogs vd ON d.dog_id = vd.dog_id
    WHERE vd.video_id = ?
    ''', (video_id,)).fetchall()
    
    # Get trip/series information
    series_info = conn.execute('''
    SELECT t.trip_id, t.trip_name, vv.part_number, vv.version_type, vv.total_parts,
           COUNT(vv2.video_id) as total_videos_in_series
    FROM trips t
    JOIN video_versions vv ON t.trip_id = vv.trip_id
    LEFT JOIN video_versions vv2 ON t.trip_id = vv2.trip_id
    WHERE vv.video_id = ?
    GROUP BY t.trip_id
    ''', (video_id,)).fetchall()

    # Thematic series memberships (the series table, not trips)
    series_memberships = conn.execute('''
    SELECT s.series_id, s.name, s.series_type, s.is_episodic,
           vs.episode_number
    FROM series s
    JOIN video_series vs ON s.series_id = vs.series_id
    WHERE vs.video_id = ?
    ORDER BY s.series_type, s.name
    ''', (video_id,)).fetchall()

    return render_template('video_detail.html', video=video, people=people,
                           dogs=dogs, series_info=series_info,
                           series_memberships=series_memberships)


@app.route('/watch/<video_id>')
def watch(video_id):
    """Night-friendly viewing surface: big embedded player + dim overlay.

    Public (no auth). Embeds YouTube's *official* IFrame player so the
    viewer's own logged-in session applies (ad-free with Premium, and the
    view still counts for the channel). We never proxy or extract streams.
    """
    conn = get_db()

    video = conn.execute(
        'SELECT * FROM videos WHERE video_id = ?', (video_id,)
    ).fetchone()

    if not video:
        abort(404)

    people = conn.execute('''
    SELECT p.person_id, p.canonical_name
    FROM people p
    JOIN video_people vp ON p.person_id = vp.person_id
    WHERE vp.video_id = ?
    ORDER BY p.canonical_name
    ''', (video_id,)).fetchall()

    dogs = conn.execute('''
    SELECT d.dog_id, d.name
    FROM dogs d
    JOIN video_dogs vd ON d.dog_id = vd.dog_id
    WHERE vd.video_id = ?
    ORDER BY d.name
    ''', (video_id,)).fetchall()

    series_memberships = conn.execute('''
    SELECT s.series_id, s.name, s.series_type, s.is_episodic,
           vs.episode_number
    FROM series s
    JOIN video_series vs ON s.series_id = vs.series_id
    WHERE vs.video_id = ?
    ORDER BY s.series_type, s.name
    ''', (video_id,)).fetchall()

    # Prefer an episodic membership that actually has an episode number --
    # that's the one that can offer Previous/Next.
    episodic = next(
        (m for m in series_memberships
         if m['is_episodic'] and m['episode_number'] is not None),
        None)

    prev_episode = next_episode = None
    episode_series = None
    related = []

    if episodic is not None:
        episode_series = episodic
        neighbour_sql = '''
        SELECT v.video_id, v.title, v.thumbnail_url, vs.episode_number
        FROM videos v
        JOIN video_series vs ON v.video_id = vs.video_id
        WHERE vs.series_id = ? AND v.deleted_at IS NULL
          AND vs.episode_number IS NOT NULL AND vs.episode_number {op} ?
        ORDER BY vs.episode_number {order}
        LIMIT 1
        '''
        params = (episodic['series_id'], episodic['episode_number'])
        prev_episode = conn.execute(
            neighbour_sql.format(op='<', order='DESC'), params).fetchone()
        next_episode = conn.execute(
            neighbour_sql.format(op='>', order='ASC'), params).fetchone()

    if prev_episode is None and next_episode is None and series_memberships:
        # Not episodic (or a one-off episode): show a small "more from this
        # series" strip instead.
        episode_series = series_memberships[0]
        related = conn.execute('''
        SELECT v.video_id, v.title, v.upload_date, v.thumbnail_url,
               v.duration, v.duration_seconds
        FROM videos v
        JOIN video_series vs ON v.video_id = vs.video_id
        WHERE vs.series_id = ? AND v.video_id != ? AND v.deleted_at IS NULL
        ORDER BY v.upload_date DESC
        LIMIT 6
        ''', (episode_series['series_id'], video_id)).fetchall()

    return render_template('watch.html', video=video, people=people,
                           dogs=dogs,
                           series_memberships=series_memberships,
                           episode_series=episode_series,
                           prev_episode=prev_episode,
                           next_episode=next_episode,
                           related=related)


@app.route('/date/<date_str>')
def date_view(date_str):
    """Videos published on a specific date"""
    try:
        # Parse date (YYYY-MM-DD format)
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return "Invalid date format. Use YYYY-MM-DD", 400
    
    conn = get_db()
    
    videos = conn.execute('''
    SELECT video_id, title, description, upload_date, thumbnail_url
    FROM videos 
    WHERE DATE(upload_date) = ?
    ORDER BY upload_date DESC
    ''', (date_str,)).fetchall()

    return render_template('date_view.html', videos=videos, date=target_date)

@app.route('/people')
def people_list():
    """Sidebar: List all people with video counts"""
    conn = get_db()

    page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page', default_per_page=20)
    total = conn.execute('SELECT COUNT(*) FROM people').fetchone()[0]

    people = conn.execute('''
    SELECT p.person_id, p.canonical_name, COUNT(vp.video_id) as video_count
    FROM people p
    LEFT JOIN video_people vp ON p.person_id = vp.person_id
    GROUP BY p.person_id, p.canonical_name
    ORDER BY video_count DESC, p.canonical_name ASC
    LIMIT ? OFFSET ?
    ''', (per_page, offset)).fetchall()
    
    # Calculate stats for template (on all people, not just the page)
    all_people = conn.execute('''SELECT p.canonical_name, COUNT(vp.video_id) as video_count FROM people p LEFT JOIN video_people vp ON p.person_id = vp.person_id GROUP BY p.person_id''').fetchall()
    family_count = sum(1 for p in all_people if p['canonical_name'].startswith("Matthew's"))
    collaborator_count = sum(1 for p in all_people if not p['canonical_name'].startswith("Matthew's") and p['canonical_name'] != 'Matthew Posa')
    most_featured = max(all_people, key=lambda x: x['video_count']) if all_people else None

    pagination = Pagination(page=page, per_page=per_page, total=total, css_framework='bootstrap4', record_name='people')
    
    return render_template('people_list.html', 
                         people=people, 
                         pagination=pagination,
                         family_count=family_count,
                         collaborator_count=collaborator_count,
                         most_featured=most_featured)

@app.route('/person/<int:person_id>')
def person_detail(person_id):
    """Person detail page with bio and videos"""
    conn = get_db()
    
    # Get person details
    person = conn.execute('''
    SELECT * FROM people WHERE person_id = ?
    ''', (person_id,)).fetchone()
    
    if not person:
        abort(404)
    
    # Paginate their videos
    videos_query = '''
    SELECT v.video_id, v.title, v.upload_date, v.thumbnail_url
    FROM videos v
    JOIN video_people vp ON v.video_id = vp.video_id
    WHERE vp.person_id = ?
    ORDER BY v.upload_date DESC
    '''
    count_query = 'SELECT COUNT(*) FROM video_people WHERE person_id = ?'
    videos, pagination = paginate(conn, videos_query, (person_id,), count_query, (person_id,))

    return render_template('person_detail.html', person=person, videos=videos, pagination=pagination)

@app.route('/dogs')
def dogs_list():
    """Sidebar: List all dogs with video counts"""
    conn = get_db()
    
    page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page', default_per_page=20)
    total = conn.execute('SELECT COUNT(*) FROM dogs').fetchone()[0]

    dogs = conn.execute('''
    SELECT d.dog_id, d.name, d.breed_primary, d.color, d.description, COUNT(vd.video_id) as video_count
    FROM dogs d
    LEFT JOIN video_dogs vd ON d.dog_id = vd.dog_id
    GROUP BY d.dog_id, d.name, d.breed_primary, d.color, d.description
    ORDER BY video_count DESC, d.name ASC
    LIMIT ? OFFSET ?
    ''', (per_page, offset)).fetchall()
    
    # Calculate stats for template (on all dogs)
    all_dogs = conn.execute('''
    SELECT d.dog_id, d.name, COUNT(vd.video_id) as video_count
    FROM dogs d
    LEFT JOIN video_dogs vd ON d.dog_id = vd.dog_id
    GROUP BY d.dog_id, d.name
    ''').fetchall()
    total_adventures = sum(d['video_count'] for d in all_dogs)
    most_featured = max(all_dogs, key=lambda x: x['video_count']) if all_dogs else None

    pagination = Pagination(page=page, per_page=per_page, total=total, css_framework='bootstrap4', record_name='dogs')
    
    return render_template('dogs_list.html', 
                         dogs=dogs,
                         pagination=pagination,
                         total_adventures=total_adventures,
                         most_featured=most_featured)

@app.route('/dog/<int:dog_id>')
def dog_detail(dog_id):
    """Dog detail page with info and videos"""
    conn = get_db()
    
    # Get dog details
    dog = conn.execute('''
    SELECT * FROM dogs WHERE dog_id = ?
    ''', (dog_id,)).fetchone()
    
    if not dog:
        abort(404)
    
    # Paginate their videos
    videos_query = '''
    SELECT v.video_id, v.title, v.upload_date, v.thumbnail_url
    FROM videos v
    JOIN video_dogs vd ON v.video_id = vd.video_id
    WHERE vd.dog_id = ?
    ORDER BY v.upload_date DESC
    '''
    count_query = 'SELECT COUNT(*) FROM video_dogs WHERE dog_id = ?'
    videos, pagination = paginate(conn, videos_query, (dog_id,), count_query, (dog_id,))

    return render_template('dog_detail.html', dog=dog, videos=videos, pagination=pagination)

# Display order + headings for the series_type groups on /series. The series
# table (not trips) is the source of truth for thematic groupings; trips are
# reserved for genuine multi-part trips.
SERIES_TYPE_GROUPS = [
    ('activity', '🏃 Adventure Types'),
    ('location', '📍 Places'),
    ('content', '🎭 Shows & Community'),
    ('special', '🎉 Special'),
]


@app.route('/series')
def series_list():
    """List every populated series, grouped by series_type."""
    conn = get_db()

    rows = conn.execute('''
    SELECT s.series_id, s.name, s.description, s.is_episodic, s.series_type,
           COUNT(vs.video_id) as video_count
    FROM series s
    JOIN video_series vs ON s.series_id = vs.series_id
    JOIN videos v ON v.video_id = vs.video_id AND v.deleted_at IS NULL
    GROUP BY s.series_id
    ORDER BY video_count DESC, s.name ASC
    ''').fetchall()

    # Empty series are hidden entirely (the JOIN above already does that).
    grouped = []
    for series_type, heading in SERIES_TYPE_GROUPS:
        members = [r for r in rows if r['series_type'] == series_type]
        if members:
            grouped.append({'series_type': series_type, 'heading': heading,
                            'series': members})

    total_series = len(rows)
    total_memberships = sum(r['video_count'] for r in rows)
    largest_series = rows[0] if rows else None

    return render_template('series_list.html',
                           grouped_series=grouped,
                           total_series=total_series,
                           total_memberships=total_memberships,
                           largest_series=largest_series)


@app.route('/series/<int:series_id>')
def series_detail(series_id):
    """Series detail page listing every video in the series."""
    conn = get_db()

    series = conn.execute(
        'SELECT * FROM series WHERE series_id = ?', (series_id,)
    ).fetchone()

    if not series:
        abort(404)

    # Episodic series read in episode order (unnumbered entries -- e.g. Hike
    # and Cook -- fall back to upload date); everything else newest first.
    if series['is_episodic']:
        order_by = ('ORDER BY vs.episode_number IS NULL, vs.episode_number ASC, '
                    'v.upload_date ASC')
    else:
        order_by = 'ORDER BY v.upload_date DESC'

    videos_query = f'''
    SELECT v.video_id, v.title, v.upload_date, v.thumbnail_url, v.duration,
           v.duration_seconds, vs.episode_number, vs.notes
    FROM videos v
    JOIN video_series vs ON v.video_id = vs.video_id
    WHERE vs.series_id = ? AND v.deleted_at IS NULL
    {order_by}
    '''
    count_query = ('SELECT COUNT(*) FROM video_series vs '
                   'JOIN videos v ON v.video_id = vs.video_id '
                   'WHERE vs.series_id = ? AND v.deleted_at IS NULL')
    videos, pagination = paginate(conn, videos_query, (series_id,),
                                  count_query, (series_id,))

    return render_template('series_detail.html',
                           series=series,
                           videos=videos,
                           pagination=pagination)

@app.route('/trips')
def trips_list():
    """List all multi-day adventure trips"""
    conn = get_db()
    
    page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page', default_per_page=20)
    total = conn.execute("SELECT COUNT(*) FROM trips WHERE series_type = 'trip'").fetchone()[0]

    trips = conn.execute('''
    SELECT t.trip_id, t.trip_name, t.start_date, t.end_date, t.description,
           COUNT(vv.video_id) as video_count,
           MIN(vv.part_number) as first_part,
           MAX(vv.part_number) as last_part,
           GROUP_CONCAT(vv.version_type) as version_types
    FROM trips t
    LEFT JOIN video_versions vv ON t.trip_id = vv.trip_id
    WHERE t.series_type = 'trip'
    GROUP BY t.trip_id
    ORDER BY t.start_date DESC
    LIMIT ? OFFSET ?
    ''', (per_page, offset)).fetchall()
    
    # Calculate stats
    all_trips = conn.execute("""SELECT t.trip_name, COUNT(vv.video_id) as video_count FROM trips t LEFT JOIN video_versions vv ON t.trip_id = vv.trip_id WHERE t.series_type = 'trip' GROUP BY t.trip_id""").fetchall()
    total_adventures = sum(t['video_count'] for t in all_trips)
    longest_trip = max(all_trips, key=lambda x: x['video_count']) if all_trips else None

    pagination = Pagination(page=page, per_page=per_page, total=total, css_framework='bootstrap4', record_name='trips')
    
    return render_template('trips_list.html', 
                         trips=trips,
                         pagination=pagination,
                         total_adventures=total_adventures,
                         longest_trip=longest_trip)

@app.route('/trip/<int:trip_id>')
def trip_detail(trip_id):
    """Trip detail page showing all parts in order"""
    conn = get_db()
    
    # Get trip details
    trip = conn.execute('''
    SELECT * FROM trips WHERE trip_id = ?
    ''', (trip_id,)).fetchone()
    
    if not trip:
        abort(404)
    
    # Get all videos in this trip
    videos_query = '''
    SELECT v.video_id, v.title, v.upload_date, v.thumbnail_url, v.duration,
           v.duration_seconds,
           vv.part_number, vv.version_type, vv.total_parts
    FROM videos v
    JOIN video_versions vv ON v.video_id = vv.video_id
    WHERE vv.trip_id = ?
    ORDER BY vv.part_number ASC
    '''
    count_query = 'SELECT COUNT(*) FROM video_versions WHERE trip_id = ?'
    videos, pagination = paginate(conn, videos_query, (trip_id,), count_query, (trip_id,))
    
    # Get trip duration in days
    if trip['start_date'] and trip['end_date']:
        from datetime import datetime
        start = datetime.fromisoformat(trip['start_date'])
        end = datetime.fromisoformat(trip['end_date'])
        duration_days = (end - start).days
    else:
        duration_days = 0

    return render_template('trip_detail.html', 
                         trip=trip, 
                         videos=videos, 
                         pagination=pagination,
                         duration_days=duration_days)

@app.route('/search')
def search():
    """Search videos by title and description"""
    query = request.args.get('q', '').strip()
    
    if not query:
        return render_template('search_results.html', videos=[],
                               transcript_hits=[], query=query)

    conn = get_db()

    # Sanitize the query for FTS5: escape double quotes and wrap in double quotes
    # to treat the entire search as a single phrase.
    sanitized_query = f'"' + query.replace('"', '""') + '"'

    # Use the FTS table for fast text search
    videos = conn.execute('''
    SELECT v.video_id, v.title, v.description, v.upload_date, v.thumbnail_url
    FROM videos_fts f
    JOIN videos v ON f.rowid = v.rowid
    WHERE f.videos_fts MATCH ?
    ORDER BY v.upload_date DESC
    ''', (sanitized_query,)).fetchall()

    transcript_hits = search_transcripts(conn, sanitized_query)

    return render_template('search_results.html', videos=videos,
                           transcript_hits=transcript_hits, query=query)


TRANSCRIPT_HIT_LIMIT = 10

#: A video can hold two transcripts at once: the YouTube auto-captions
#: (scripts/ingest_transcripts.py) and the Whisper large-v3 re-transcription
#: (scripts/pipeline/). Whisper is the better witness -- higher precision,
#: real punctuation, and it is the text the adjudicator has corrected -- so
#: search prefers it *per video*. The YouTube rows are never deleted: a video
#: that has not been re-transcribed yet keeps searching exactly as before.
PREFERRED_TRANSCRIPT_SOURCE = 'whisper-large-v3'

# Anded into the FTS query. The subselect is evaluated once, not per row.
_PREFER_WHISPER_SQL = '''
          AND (s.source = ?
               OR s.video_id NOT IN (SELECT video_id FROM transcript_segments
                                     WHERE source = ?))
'''


def search_transcripts(conn, sanitized_query, limit=TRANSCRIPT_HIT_LIMIT):
    """Return the best-ranked transcript segment per video for an FTS query.

    ``sanitized_query`` is the already-escaped FTS5 phrase used for
    ``videos_fts``.  Returns [] when the transcript tables have not been
    created yet (migration 010 / scripts/ingest_transcripts.py) so search keeps
    working on a database without transcripts.

    Where both sources exist for a video only the Whisper segments are
    considered, so one video never produces two hits for the same moment.
    """
    # snippet() cannot be used in an aggregate/GROUP BY context, so pull the
    # top-ranked segments and keep the first (best) one per video in Python.
    base_sql = '''
        SELECT s.video_id,
               v.title,
               s.start_seconds,
               s.text,
               snippet(transcripts_fts, 0, char(2), char(3), '…', 24) AS snippet
        FROM transcripts_fts f
        JOIN transcript_segments s ON s.segment_id = f.rowid
        JOIN videos v ON v.video_id = s.video_id
        WHERE f.transcripts_fts MATCH ?
        {preference}
        ORDER BY f.rank
        LIMIT ?
    '''
    try:
        rows = conn.execute(
            base_sql.format(preference=_PREFER_WHISPER_SQL),
            (sanitized_query, PREFERRED_TRANSCRIPT_SOURCE,
             PREFERRED_TRANSCRIPT_SOURCE, limit * 20)).fetchall()
    except sqlite3.OperationalError:
        # No `source` column yet (pre-migration-013 database): fall back to the
        # unfiltered query rather than losing transcript search entirely.
        try:
            rows = conn.execute(base_sql.format(preference=''),
                                (sanitized_query, limit * 20)).fetchall()
        except sqlite3.OperationalError:
            return []

    hits = []
    seen = set()
    for row in rows:
        if row['video_id'] in seen:
            continue
        seen.add(row['video_id'])
        if len(hits) >= limit:
            break
        start = int(row['start_seconds'] or 0)
        # snippet() marks the match with control characters so the surrounding
        # transcript text can be HTML-escaped before the <mark> tags go in.
        snippet = escape(row['snippet'] or row['text'])
        snippet = Markup(
            str(snippet).replace('\x02', '<mark>').replace('\x03', '</mark>')
        )
        hits.append({
            'video_id': row['video_id'],
            'title': row['title'],
            'start_seconds': start,
            'timestamp': format_seconds(start),
            'text': row['text'],
            'snippet': snippet,
            'youtube_url': (
                f"https://www.youtube.com/watch?v={row['video_id']}&t={start}s"
            ),
        })
    return hits


# Flask CLI Commands
@app.cli.command('create-admin')
def create_admin():
    """Create a new admin user via CLI

    Usage: flask create-admin
    """
    import click

    click.echo('Create Admin User')
    click.echo('=' * 40)

    username = click.prompt('Username', type=str)
    email = click.prompt('Email', type=str)
    password = click.prompt('Password', hide_input=True, confirmation_prompt=True)

    # Validate inputs
    if not username or not email or not password:
        click.echo('Error: All fields are required', err=True)
        return

    # Create user
    conn = get_db()
    try:
        # Check if username exists
        existing = conn.execute('SELECT user_id FROM users WHERE username = ?', (username,)).fetchone()
        if existing:
            click.echo(f'Error: Username "{username}" already exists', err=True)
            return

        # Check if email exists
        existing = conn.execute('SELECT user_id FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            click.echo(f'Error: Email "{email}" already exists', err=True)
            return

        # Create admin user
        user = User.create(username, email, password, role='admin', db_conn=conn)
        click.echo(f'\n✓ Admin user created successfully!')
        click.echo(f'  Username: {user.username}')
        click.echo(f'  Email: {user.email}')
        click.echo(f'  Role: {user.role}')
        click.echo(f'  User ID: {user.user_id}\n')

    except Exception as e:
        click.echo(f'Error creating user: {e}', err=True)
    # Connection is closed by the app-context teardown handler (see db.py).


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)

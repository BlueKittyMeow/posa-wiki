#!/usr/bin/env python3
"""
Posa Wiki - Flask Web Interface
Dark hacker girl aesthetic with fairyfloss theme and rounded edges
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_paginate import Pagination, get_page_args
from flask_login import LoginManager, current_user
from flask_wtf import CSRFProtect
import sqlite3
import json
from datetime import datetime, timedelta
import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import CONFIG_BY_NAME, Config
from models.user import User

def from_json(value):
    """Template filter to parse JSON strings"""
    if value and value != 'null':
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    return []

def format_duration(duration_str):
    """Format duration string to readable format"""
    if not duration_str:
        return "Unknown"
    
    # If already formatted (MM:SS or HH:MM:SS), return as-is
    if ':' in duration_str:
        return duration_str
    
    # Handle ISO 8601 format (PT#M#S)
    try:
        duration_str = duration_str.replace('PT', '')
        minutes = 0
        seconds = 0
        
        if 'M' in duration_str:
            minutes = int(duration_str.split('M')[0])
            duration_str = duration_str.split('M')[1] if 'M' in duration_str else duration_str
        
        if 'S' in duration_str:
            seconds = int(duration_str.replace('S', ''))
        
        if minutes > 0:
            return f"{minutes}:{seconds:02d}"
        else:
            return f"0:{seconds:02d}"
    except:
        return duration_str


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

csrf = CSRFProtect()
csrf.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'


@login_manager.user_loader
def load_user(user_id):
    """Load user for Flask-Login session management"""
    conn = get_db_connection()
    user = User.get_by_id(user_id, conn)
    conn.close()
    return user


@app.context_processor
def inject_sidebar_data():
    """Inject data for the sidebar into all templates"""
    conn = get_db_connection()
    
    sidebar_people = conn.execute('''
        SELECT p.person_id, p.canonical_name, COUNT(vp.video_id) as video_count
        FROM people p
        LEFT JOIN video_people vp ON p.person_id = vp.person_id
        GROUP BY p.person_id, p.canonical_name
        ORDER BY video_count DESC
    ''').fetchall()
    
    sidebar_dogs = conn.execute('''
        SELECT d.dog_id, d.name, COUNT(vd.video_id) as video_count
        FROM dogs d
        LEFT JOIN video_dogs vd ON d.dog_id = vd.dog_id
        GROUP BY d.dog_id, d.name
        ORDER BY video_count DESC
    ''').fetchall()
    
    conn.close()
    
    return dict(sidebar_people=sidebar_people, sidebar_dogs=sidebar_dogs)


# Register blueprints
from blueprints.auth import auth_bp
app.register_blueprint(auth_bp)


# Register template filters
app.jinja_env.filters['from_json'] = from_json
app.jinja_env.filters['format_duration'] = format_duration

# Add timedelta to template globals for date navigation
app.jinja_env.globals['timedelta'] = timedelta

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(app.config['DATABASE_PATH'])
    conn.row_factory = sqlite3.Row  # Return rows as dicts
    return conn

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
    conn = get_db_connection()
    
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
    
    conn.close()
    
    return render_template('index.html', recent_videos=recent_videos, stats=stats)

@app.route('/videos')
def video_list():
    """Sortable video list with thumbnails"""
    sort_by = request.args.get('sort', 'upload_date')
    order = request.args.get('order', 'desc')
    
    conn = get_db_connection()
    
    # Pagination
    page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page', default_per_page=20)
    
    # Get total number of videos for pagination
    total = conn.execute('SELECT COUNT(*) FROM videos').fetchone()[0]
    
    # Build SQL query with sorting and pagination
    order_sql = 'ASC' if order == 'asc' else 'DESC'
    valid_sorts = ['upload_date', 'title', 'duration', 'view_count']
    if sort_by not in valid_sorts:
        sort_by = 'upload_date'
    
    query = f'''
    SELECT video_id, title, description, upload_date, duration, 
           view_count, thumbnail_url
    FROM videos 
    ORDER BY {sort_by} {order_sql}
    LIMIT ? OFFSET ?
    '''
    
    videos = conn.execute(query, (per_page, offset)).fetchall()
    conn.close()
    
    pagination = Pagination(page=page, per_page=per_page, total=total,
                            css_framework='bootstrap4',
                            record_name='videos')
    
    return render_template('video_list.html', 
                         videos=videos, 
                         sort_by=sort_by, 
                         order=order,
                         pagination=pagination)

@app.route('/video/<video_id>')
def video_detail(video_id):
    """Video detail page with metadata and related videos"""
    conn = get_db_connection()
    
    # Get video details
    video = conn.execute('''
    SELECT * FROM videos WHERE video_id = ?
    ''', (video_id,)).fetchone()
    
    if not video:
        return "Video not found", 404
    
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
    
    conn.close()
    
    return render_template('video_detail.html', video=video, people=people, dogs=dogs, series_info=series_info)

@app.route('/date/<date_str>')
def date_view(date_str):
    """Videos published on a specific date"""
    try:
        # Parse date (YYYY-MM-DD format)
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return "Invalid date format. Use YYYY-MM-DD", 400
    
    conn = get_db_connection()
    
    videos = conn.execute('''
    SELECT video_id, title, description, upload_date, thumbnail_url
    FROM videos 
    WHERE DATE(upload_date) = ?
    ORDER BY upload_date DESC
    ''', (date_str,)).fetchall()
    
    conn.close()
    
    return render_template('date_view.html', videos=videos, date=target_date)

@app.route('/people')
def people_list():
    """Sidebar: List all people with video counts"""
    conn = get_db_connection()

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
    
    conn.close()

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
    conn = get_db_connection()
    
    # Get person details
    person = conn.execute('''
    SELECT * FROM people WHERE person_id = ?
    ''', (person_id,)).fetchone()
    
    if not person:
        return "Person not found", 404
    
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

    conn.close()
    
    return render_template('person_detail.html', person=person, videos=videos, pagination=pagination)

@app.route('/dogs')
def dogs_list():
    """Sidebar: List all dogs with video counts"""
    conn = get_db_connection()
    
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
    
    conn.close()

    pagination = Pagination(page=page, per_page=per_page, total=total, css_framework='bootstrap4', record_name='dogs')
    
    return render_template('dogs_list.html', 
                         dogs=dogs,
                         pagination=pagination,
                         total_adventures=total_adventures,
                         most_featured=most_featured)

@app.route('/dog/<int:dog_id>')
def dog_detail(dog_id):
    """Dog detail page with info and videos"""
    conn = get_db_connection()
    
    # Get dog details
    dog = conn.execute('''
    SELECT * FROM dogs WHERE dog_id = ?
    ''', (dog_id,)).fetchone()
    
    if not dog:
        return "Dog not found", 404
    
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
    
    conn.close()
    
    return render_template('dog_detail.html', dog=dog, videos=videos, pagination=pagination)

@app.route('/series')
def series_list():
    """List all episodic series"""
    conn = get_db_connection()
    
    page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page', default_per_page=20)
    total = conn.execute("SELECT COUNT(*) FROM trips WHERE series_type = 'series'").fetchone()[0]

    series = conn.execute('''
    SELECT t.trip_id, t.trip_name, t.start_date, t.end_date, t.description,
           COUNT(vv.video_id) as video_count,
           MIN(vv.part_number) as first_episode,
           MAX(vv.part_number) as last_episode
    FROM trips t
    LEFT JOIN video_versions vv ON t.trip_id = vv.trip_id
    WHERE t.series_type = 'series'
    GROUP BY t.trip_id
    ORDER BY t.start_date DESC
    LIMIT ? OFFSET ?
    ''', (per_page, offset)).fetchall()
    
    # Calculate stats
    all_series = conn.execute("""SELECT t.trip_name, COUNT(vv.video_id) as video_count FROM trips t LEFT JOIN video_versions vv ON t.trip_id = vv.trip_id WHERE t.series_type = 'series' GROUP BY t.trip_id""").fetchall()
    total_episodes = sum(s['video_count'] for s in all_series)
    longest_series = max(all_series, key=lambda x: x['video_count']) if all_series else None
    
    conn.close()

    pagination = Pagination(page=page, per_page=per_page, total=total, css_framework='bootstrap4', record_name='series')
    
    return render_template('series_list.html', 
                         series=series,
                         pagination=pagination,
                         total_episodes=total_episodes,
                         longest_series=longest_series)

@app.route('/trips')
def trips_list():
    """List all multi-day adventure trips"""
    conn = get_db_connection()
    
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
    
    conn.close()

    pagination = Pagination(page=page, per_page=per_page, total=total, css_framework='bootstrap4', record_name='trips')
    
    return render_template('trips_list.html', 
                         trips=trips,
                         pagination=pagination,
                         total_adventures=total_adventures,
                         longest_trip=longest_trip)

@app.route('/trip/<int:trip_id>')
def trip_detail(trip_id):
    """Trip detail page showing all parts in order"""
    conn = get_db_connection()
    
    # Get trip details
    trip = conn.execute('''
    SELECT * FROM trips WHERE trip_id = ?
    ''', (trip_id,)).fetchone()
    
    if not trip:
        return "Trip not found", 404
    
    # Get all videos in this trip
    videos_query = '''
    SELECT v.video_id, v.title, v.upload_date, v.thumbnail_url, v.duration,
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
    
    conn.close()
    
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
        return render_template('search_results.html', videos=[], query=query)
    
    conn = get_db_connection()
    
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
    
    conn.close()
    
    return render_template('search_results.html', videos=videos, query=query)


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
    conn = get_db_connection()
    try:
        # Check if username exists
        existing = conn.execute('SELECT user_id FROM users WHERE username = ?', (username,)).fetchone()
        if existing:
            click.echo(f'Error: Username "{username}" already exists', err=True)
            conn.close()
            return

        # Check if email exists
        existing = conn.execute('SELECT user_id FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            click.echo(f'Error: Email "{email}" already exists', err=True)
            conn.close()
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
    finally:
        conn.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
#!/usr/bin/env python3
"""
Posa Wiki - Flask Web Interface
Dark hacker girl aesthetic with fairyfloss theme and rounded edges
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
import json
from datetime import datetime, timedelta
import os

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

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management later

# Register template filters
app.jinja_env.filters['from_json'] = from_json
app.jinja_env.filters['format_duration'] = format_duration

# Add timedelta to template globals for date navigation
app.jinja_env.globals['timedelta'] = timedelta

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect('posa_wiki.db')
    conn.row_factory = sqlite3.Row  # Return rows as dicts
    return conn

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
    
    # Build SQL query with sorting
    order_sql = 'ASC' if order == 'asc' else 'DESC'
    valid_sorts = ['upload_date', 'title', 'duration', 'view_count']
    if sort_by not in valid_sorts:
        sort_by = 'upload_date'
    
    query = f'''
    SELECT video_id, title, description, upload_date, duration, 
           view_count, thumbnail_url
    FROM videos 
    ORDER BY {sort_by} {order_sql}
    '''
    
    videos = conn.execute(query).fetchall()
    conn.close()
    
    return render_template('video_list.html', videos=videos, sort_by=sort_by, order=order)

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
    
    people = conn.execute('''
    SELECT p.person_id, p.canonical_name, COUNT(vp.video_id) as video_count
    FROM people p
    LEFT JOIN video_people vp ON p.person_id = vp.person_id
    GROUP BY p.person_id, p.canonical_name
    ORDER BY video_count DESC, p.canonical_name ASC
    ''').fetchall()
    
    # Calculate stats for template
    family_count = sum(1 for p in people if p['canonical_name'].startswith("Matthew's"))
    collaborator_count = sum(1 for p in people if not p['canonical_name'].startswith("Matthew's") and p['canonical_name'] != 'Matthew Posa')
    most_featured = max(people, key=lambda x: x['video_count']) if people else None
    
    conn.close()
    
    return render_template('people_list.html', 
                         people=people, 
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
    
    # Get their videos
    videos = conn.execute('''
    SELECT v.video_id, v.title, v.upload_date, v.thumbnail_url
    FROM videos v
    JOIN video_people vp ON v.video_id = vp.video_id
    WHERE vp.person_id = ?
    ORDER BY v.upload_date DESC
    ''', (person_id,)).fetchall()
    
    conn.close()
    
    return render_template('person_detail.html', person=person, videos=videos)

@app.route('/dogs')
def dogs_list():
    """Sidebar: List all dogs with video counts"""
    conn = get_db_connection()
    
    dogs = conn.execute('''
    SELECT d.dog_id, d.name, d.breed_primary, d.color, d.description, COUNT(vd.video_id) as video_count
    FROM dogs d
    LEFT JOIN video_dogs vd ON d.dog_id = vd.dog_id
    GROUP BY d.dog_id, d.name, d.breed_primary, d.color, d.description
    ORDER BY video_count DESC, d.name ASC
    ''').fetchall()
    
    # Calculate stats for template
    total_adventures = sum(d['video_count'] for d in dogs)
    most_featured = max(dogs, key=lambda x: x['video_count']) if dogs else None
    
    conn.close()
    
    return render_template('dogs_list.html', 
                         dogs=dogs,
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
    
    # Get their videos
    videos = conn.execute('''
    SELECT v.video_id, v.title, v.upload_date, v.thumbnail_url
    FROM videos v
    JOIN video_dogs vd ON v.video_id = vd.video_id
    WHERE vd.dog_id = ?
    ORDER BY v.upload_date DESC
    ''', (dog_id,)).fetchall()
    
    conn.close()
    
    return render_template('dog_detail.html', dog=dog, videos=videos)

@app.route('/series')
def series_list():
    """List all episodic series"""
    conn = get_db_connection()
    
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
    ''').fetchall()
    
    # Calculate stats
    total_episodes = sum(s['video_count'] for s in series)
    longest_series = max(series, key=lambda x: x['video_count']) if series else None
    
    conn.close()
    
    return render_template('series_list.html', 
                         series=series,
                         total_episodes=total_episodes,
                         longest_series=longest_series)

@app.route('/trips')
def trips_list():
    """List all multi-day adventure trips"""
    conn = get_db_connection()
    
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
    ''').fetchall()
    
    # Calculate stats
    total_adventures = sum(t['video_count'] for t in trips)
    longest_trip = max(trips, key=lambda x: x['video_count']) if trips else None
    
    conn.close()
    
    return render_template('trips_list.html', 
                         trips=trips,
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
    videos = conn.execute('''
    SELECT v.video_id, v.title, v.upload_date, v.thumbnail_url, v.duration,
           vv.part_number, vv.version_type, vv.total_parts
    FROM videos v
    JOIN video_versions vv ON v.video_id = vv.video_id
    WHERE vv.trip_id = ?
    ORDER BY vv.part_number ASC
    ''', (trip_id,)).fetchall()
    
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
                         duration_days=duration_days)

@app.route('/search')
def search():
    """Search videos by title and description"""
    query = request.args.get('q', '').strip()
    
    if not query:
        return render_template('search_results.html', videos=[], query=query)
    
    conn = get_db_connection()
    
    # Simple text search across title and description
    videos = conn.execute('''
    SELECT video_id, title, description, upload_date, thumbnail_url
    FROM videos 
    WHERE title LIKE ? OR description LIKE ?
    ORDER BY upload_date DESC
    ''', (f'%{query}%', f'%{query}%')).fetchall()
    
    conn.close()
    
    return render_template('search_results.html', videos=videos, query=query)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
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
    """Format ISO 8601 duration string to readable format"""
    if not duration_str:
        return "Unknown"
    
    # Simple parsing for PT#M#S format
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
           view_count, like_count, thumbnail_url
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
    
    conn.close()
    
    return render_template('video_detail.html', video=video, people=people, dogs=dogs)

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
    
    conn.close()
    
    return render_template('people_list.html', people=people)

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
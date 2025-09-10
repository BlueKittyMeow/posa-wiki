#!/usr/bin/env python3
"""
Import videos from JSON scrape data into SQLite database.
Includes tag validation and separation of validated/unvalidated tags.
"""

import sqlite3
import json
from datetime import datetime
from collections import Counter

def load_tag_authorities():
    """Load tag authority system for validation"""
    with open('tag_authority_system.json', 'r') as f:
        data = json.load(f)
    
    # Create alias lookup
    alias_to_authority = {}
    for auth in data['authorities']:
        canonical = auth['canonical_name']
        for alias in auth['aliases']:
            alias_to_authority[alias.lower()] = canonical
    
    print(f"📋 Loaded {len(data['authorities'])} authorities with {len(alias_to_authority)} aliases")
    return alias_to_authority

def validate_tags(video_tags, alias_to_authority):
    """Separate tags into validated (canonical) and unvalidated arrays"""
    if not video_tags:
        return [], []
    
    validated_tags = []
    unvalidated_tags = []
    
    for tag in video_tags:
        tag_lower = tag.lower().strip()
        
        if tag_lower in alias_to_authority:
            canonical_name = alias_to_authority[tag_lower]
            if canonical_name not in validated_tags:
                validated_tags.append(canonical_name)
        else:
            if tag not in unvalidated_tags:
                unvalidated_tags.append(tag)
    
    return validated_tags, unvalidated_tags

def parse_duration(duration_str):
    """Convert YouTube ISO 8601 duration to readable format"""
    if not duration_str:
        return None
    
    # Handle PT1H36M19S -> 1:36:19 or PT4M19S -> 4:19 conversion
    if duration_str.startswith('PT'):
        duration_str = duration_str[2:]  # Remove PT
        
        hours = 0
        minutes = 0
        seconds = 0
        
        # Parse hours
        if 'H' in duration_str:
            parts = duration_str.split('H')
            hours = int(parts[0])
            duration_str = parts[1] if len(parts) > 1 else ''
        
        # Parse minutes
        if 'M' in duration_str:
            parts = duration_str.split('M')
            minutes = int(parts[0])
            duration_str = parts[1] if len(parts) > 1 else ''
        
        # Parse seconds
        if 'S' in duration_str and duration_str != 'S':
            seconds = int(duration_str.replace('S', ''))
        
        # Format based on presence of hours
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    
    return duration_str

def import_videos():
    """Import all videos from JSON into database with tag validation"""
    
    # Load video data
    print("📥 Loading video data...")
    with open('complete_channel_scrape_20250909_122145.json', 'r') as f:
        video_data = json.load(f)
    
    videos = video_data['videos']
    print(f"   Found {len(videos)} videos to import")
    
    # Load tag authorities
    alias_to_authority = load_tag_authorities()
    
    # Connect to database
    conn = sqlite3.connect('posa_wiki.db')
    cursor = conn.cursor()
    
    print("🏗️  Importing videos with tag validation...")
    
    imported_count = 0
    validation_stats = {
        'total_videos_with_tags': 0,
        'total_original_tags': 0,
        'total_validated_tags': 0,
        'total_unvalidated_tags': 0
    }
    
    for video in videos:
        snippet = video.get('snippet', {})
        statistics = video.get('statistics', {})
        content_details = video.get('contentDetails', {})
        
        # Extract basic video data
        video_id = video['id']
        title = snippet.get('title', '')
        upload_date = snippet.get('publishedAt', '')[:10] if snippet.get('publishedAt') else None
        duration = parse_duration(content_details.get('duration'))
        view_count = int(statistics.get('viewCount', 0)) if statistics.get('viewCount') else 0
        description = snippet.get('description', '')
        thumbnail_url = snippet.get('thumbnails', {}).get('high', {}).get('url', '')
        
        # Get original tags
        original_tags = snippet.get('tags', [])
        
        # Validate tags
        validated_tags, unvalidated_tags = validate_tags(original_tags, alias_to_authority)
        
        # Update stats
        if original_tags:
            validation_stats['total_videos_with_tags'] += 1
            validation_stats['total_original_tags'] += len(original_tags)
            validation_stats['total_validated_tags'] += len(validated_tags)
            validation_stats['total_unvalidated_tags'] += len(unvalidated_tags)
        
        # Insert video
        cursor.execute('''
        INSERT OR REPLACE INTO videos (
            video_id, title, upload_date, duration, view_count, description, 
            thumbnail_url, youtube_tags, validated_tags, unvalidated_tags,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            video_id,
            title,
            upload_date,
            duration,
            view_count,
            description,
            thumbnail_url,
            json.dumps(original_tags),
            json.dumps(validated_tags),
            json.dumps(unvalidated_tags),
            datetime.now().isoformat(),
            datetime.now().isoformat()
        ))
        
        imported_count += 1
        
        if imported_count % 50 == 0:
            print(f"   Imported {imported_count}/{len(videos)} videos...")
    
    conn.commit()
    
    print("📊 Import Statistics:")
    print(f"   Videos imported: {imported_count}")
    print(f"   Videos with tags: {validation_stats['total_videos_with_tags']}")
    print(f"   Original tags: {validation_stats['total_original_tags']}")
    print(f"   Validated tags: {validation_stats['total_validated_tags']}")
    print(f"   Unvalidated tags: {validation_stats['total_unvalidated_tags']}")
    
    # Calculate validation coverage
    if validation_stats['total_original_tags'] > 0:
        validation_rate = (validation_stats['total_validated_tags'] / validation_stats['total_original_tags']) * 100
        print(f"   Tag validation rate: {validation_rate:.1f}%")
    
    # Show some examples
    print("\n🔍 Sample imported data:")
    cursor.execute('''
    SELECT video_id, title, upload_date, duration, 
           json_array_length(validated_tags) as validated_count,
           json_array_length(unvalidated_tags) as unvalidated_count
    FROM videos 
    WHERE json_array_length(youtube_tags) > 0
    ORDER BY upload_date DESC 
    LIMIT 5
    ''')
    
    for row in cursor.fetchall():
        video_id, title, upload_date, duration, val_count, unval_count = row
        print(f"   {video_id}: {title[:50]}... ({duration}) - {val_count} validated, {unval_count} unvalidated tags")
    
    # Show top validated tags
    print("\n🏷️  Top validated tags across all videos:")
    cursor.execute('''
    SELECT json_extract(value, '$') as tag, COUNT(*) as count
    FROM videos, json_each(validated_tags)
    WHERE validated_tags != '[]'
    GROUP BY tag
    ORDER BY count DESC
    LIMIT 10
    ''')
    
    for tag, count in cursor.fetchall():
        print(f"   {tag}: {count} videos")
    
    conn.close()
    print(f"\n🎉 Successfully imported {imported_count} videos into posa_wiki.db!")

if __name__ == "__main__":
    import_videos()
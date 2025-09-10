#!/usr/bin/env python3
"""
Import the missing 19 videos into database with tag validation.
"""

import sqlite3
import json
from datetime import datetime

def load_tag_authorities():
    """Load tag authority system for validation"""
    with open('tag_authority_system.json', 'r') as f:
        data = json.load(f)
    
    alias_to_authority = {}
    for auth in data['authorities']:
        canonical = auth['canonical_name']
        for alias in auth['aliases']:
            alias_to_authority[alias.lower()] = canonical
    
    return alias_to_authority

def validate_tags(video_tags, alias_to_authority):
    """Separate tags into validated and unvalidated arrays"""
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
    
    if duration_str.startswith('PT'):
        duration_str = duration_str[2:]
        
        hours = 0
        minutes = 0
        seconds = 0
        
        if 'H' in duration_str:
            parts = duration_str.split('H')
            hours = int(parts[0])
            duration_str = parts[1] if len(parts) > 1 else ''
        
        if 'M' in duration_str:
            parts = duration_str.split('M')
            minutes = int(parts[0])
            duration_str = parts[1] if len(parts) > 1 else ''
        
        if 'S' in duration_str and duration_str != 'S':
            seconds = int(duration_str.replace('S', ''))
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    
    return duration_str

def import_missing_videos():
    """Import missing videos from complete scrape"""
    
    # Load complete video data
    print("📥 Loading complete video data...")
    with open('complete_channel_scrape_20250909_122145.json', 'r') as f:
        complete_data = json.load(f)
    
    complete_videos = complete_data['videos']
    print(f"   Complete dataset: {len(complete_videos)} videos")
    
    # Load current database videos
    conn = sqlite3.connect('posa_wiki.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT video_id FROM videos')
    existing_ids = {row[0] for row in cursor.fetchall()}
    print(f"   Current database: {len(existing_ids)} videos")
    
    # Find missing videos
    complete_ids = {v['id'] for v in complete_videos}
    missing_ids = complete_ids - existing_ids
    
    print(f"   Missing videos to import: {len(missing_ids)}")
    
    if not missing_ids:
        print("✅ No missing videos found! Database is complete.")
        conn.close()
        return
    
    # Load tag authorities
    alias_to_authority = load_tag_authorities()
    print(f"📋 Loaded tag authority system")
    
    # Import missing videos
    print(f"🔄 Importing {len(missing_ids)} missing videos...")
    
    imported_count = 0
    validation_stats = {
        'total_videos_with_tags': 0,
        'total_original_tags': 0,
        'total_validated_tags': 0,
        'total_unvalidated_tags': 0
    }
    
    for video in complete_videos:
        if video['id'] not in missing_ids:
            continue
            
        snippet = video.get('snippet', {})
        statistics = video.get('statistics', {})
        content_details = video.get('contentDetails', {})
        
        # Extract video data
        video_id = video['id']
        title = snippet.get('title', '')
        upload_date = snippet.get('publishedAt', '')[:10] if snippet.get('publishedAt') else None
        duration = parse_duration(content_details.get('duration'))
        view_count = int(statistics.get('viewCount', 0)) if statistics.get('viewCount') else 0
        description = snippet.get('description', '')
        thumbnail_url = snippet.get('thumbnails', {}).get('high', {}).get('url', '')
        
        # Get and validate tags
        original_tags = snippet.get('tags', [])
        validated_tags, unvalidated_tags = validate_tags(original_tags, alias_to_authority)
        
        # Update stats
        if original_tags:
            validation_stats['total_videos_with_tags'] += 1
            validation_stats['total_original_tags'] += len(original_tags)
            validation_stats['total_validated_tags'] += len(validated_tags)
            validation_stats['total_unvalidated_tags'] += len(unvalidated_tags)
        
        # Insert video
        cursor.execute('''
        INSERT INTO videos (
            video_id, title, upload_date, duration, view_count, description, 
            thumbnail_url, youtube_tags, validated_tags, unvalidated_tags,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            video_id, title, upload_date, duration, view_count, description,
            thumbnail_url, json.dumps(original_tags), json.dumps(validated_tags),
            json.dumps(unvalidated_tags), datetime.now().isoformat(),
            datetime.now().isoformat()
        ))
        
        imported_count += 1
        print(f"   Imported: {video_id} - {title[:50]}...")
    
    conn.commit()
    
    # Final verification
    cursor.execute('SELECT COUNT(*) FROM videos')
    final_count = cursor.fetchone()[0]
    
    print(f"\\n📊 Import Complete!")
    print(f"   Videos imported: {imported_count}")
    print(f"   Final database count: {final_count}")
    print(f"   Expected total: 358")
    
    if final_count == 358:
        print("   ✅ PERFECT! Database now has ALL videos!")
    else:
        print(f"   ⚠️  Still missing {358 - final_count} videos")
    
    # Show some of the newly imported videos
    if imported_count > 0:
        print(f"\\n🎯 Sample newly imported videos:")
        cursor.execute('''
        SELECT video_id, title, upload_date, duration,
               json_array_length(validated_tags) as val_count,
               json_array_length(unvalidated_tags) as unval_count
        FROM videos 
        WHERE video_id IN ({})
        ORDER BY upload_date DESC 
        LIMIT 5
        '''.format(','.join(['?' for _ in missing_ids])), list(missing_ids))
        
        for row in cursor.fetchall():
            video_id, title, upload_date, duration, val_count, unval_count = row
            print(f"   {video_id}: {title[:50]}... ({duration}) - {val_count}V, {unval_count}U tags")
    
    conn.close()
    print(f"\\n🎉 Successfully imported all missing videos!")

if __name__ == "__main__":
    import_missing_videos()
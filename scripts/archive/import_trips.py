#!/usr/bin/env python3
"""
Import detected trips into database with validation.
Creates trip records and links video parts together.
"""

import sqlite3
import json
from datetime import datetime

def import_trips_to_database():
    """Import trip analysis results to database"""
    
    # Load analysis results
    with open('trip_analysis_results.json', 'r') as f:
        trips_data = json.load(f)
    
    conn = sqlite3.connect('posa_wiki.db')
    cursor = conn.cursor()
    
    print("🚀 IMPORTING TRIPS TO DATABASE")
    print("=" * 40)
    
    imported_trips = 0
    skipped_trips = 0
    
    for trip_data in trips_data:
        base_title = trip_data['base_title']
        confidence = trip_data['confidence']
        videos = trip_data['videos']
        trip_type = trip_data['type']
        
        # Skip low confidence potential series for now
        if confidence == 'low':
            print(f"⚠️  SKIPPING: {base_title} (low confidence)")
            skipped_trips += 1
            continue
        
        # Validate video count
        if len(videos) < 2:
            print(f"⚠️  SKIPPING: {base_title} (only {len(videos)} videos)")
            skipped_trips += 1
            continue
        
        # Calculate trip dates
        dates = [v['upload_date'][:10] for v in videos]
        start_date = min(dates)
        end_date = max(dates)
        
        print(f"\\n📺 IMPORTING: {base_title}")
        print(f"   Type: {trip_type}, Confidence: {confidence}")
        print(f"   Videos: {len(videos)}, Date range: {start_date} to {end_date}")
        
        # Insert trip record
        try:
            cursor.execute('''
            INSERT INTO trips (trip_name, start_date, end_date, description)
            VALUES (?, ?, ?, ?)
            ''', (
                base_title,
                start_date,
                end_date,
                f"Multi-part {trip_type} with {len(videos)} videos. Auto-detected with {confidence} confidence."
            ))
            
            trip_id = cursor.lastrowid
            
            # Link videos to trip through video_versions table
            for i, video in enumerate(videos):
                part_number = video.get('part_number', i + 1)
                
                # Determine version type
                if '[Extended Version]' in video['title']:
                    version_type = 'extended'
                elif 'Episode' in video['title']:
                    version_type = 'episode'
                elif 'Night' in video['title']:
                    version_type = 'night'
                else:
                    version_type = 'part'
                
                cursor.execute('''
                INSERT INTO video_versions 
                (trip_id, version_type, part_number, total_parts, video_id)
                VALUES (?, ?, ?, ?, ?)
                ''', (
                    trip_id,
                    version_type,
                    part_number,
                    len(videos),
                    video['video_id']
                ))
                
                print(f"   • Part {part_number}: {video['title'][:50]}...")
            
            imported_trips += 1
            
        except sqlite3.Error as e:
            print(f"   ❌ ERROR: {e}")
            skipped_trips += 1
    
    conn.commit()
    
    # Show validation results
    print(f"\\n📊 IMPORT SUMMARY:")
    print(f"   Trips imported: {imported_trips}")
    print(f"   Trips skipped: {skipped_trips}")
    
    # Check for any issues
    print(f"\\n🔍 VALIDATION CHECKS:")
    
    # Check for videos in multiple trips
    duplicate_videos = cursor.execute('''
    SELECT video_id, COUNT(*) as trip_count 
    FROM video_versions 
    GROUP BY video_id 
    HAVING trip_count > 1
    ''').fetchall()
    
    if duplicate_videos:
        print(f"   ⚠️  {len(duplicate_videos)} videos appear in multiple trips:")
        for video_id, count in duplicate_videos:
            title = cursor.execute('SELECT title FROM videos WHERE video_id = ?', (video_id,)).fetchone()[0]
            print(f"      • {title[:50]}... (in {count} trips)")
    else:
        print(f"   ✅ No duplicate video assignments")
    
    # Check for missing parts in series
    missing_parts = cursor.execute('''
    SELECT t.trip_name, t.trip_id, 
           COUNT(vv.part_number) as actual_parts,
           MAX(vv.total_parts) as expected_parts
    FROM trips t
    LEFT JOIN video_versions vv ON t.trip_id = vv.trip_id
    GROUP BY t.trip_id
    HAVING actual_parts != expected_parts
    ''').fetchall()
    
    if missing_parts:
        print(f"   ⚠️  {len(missing_parts)} trips have missing parts:")
        for trip_name, trip_id, actual, expected in missing_parts:
            print(f"      • {trip_name}: {actual}/{expected} parts")
    else:
        print(f"   ✅ All trips have complete parts")
    
    conn.close()
    
    print(f"\\n🎉 Trip import complete!")
    print(f"   Ready to build trip browsing interface")

if __name__ == "__main__":
    import_trips_to_database()
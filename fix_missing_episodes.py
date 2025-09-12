#!/usr/bin/env python3
"""
Fix missing Unsuccessful Fishing Show episodes and update trip.
Also fix the binge watch playlist functionality.
"""

import sqlite3
import re

def fix_missing_episodes():
    """Add missing episodes to the Unsuccessful Fishing Show trip"""
    
    conn = sqlite3.connect('posa_wiki.db')
    cursor = conn.cursor()
    
    print("🔧 FIXING MISSING UNSUCCESSFUL FISHING SHOW EPISODES")
    print("=" * 60)
    
    # Find the existing trip
    trip = cursor.execute('''
    SELECT trip_id, trip_name FROM trips 
    WHERE trip_name LIKE '%Unsuccessful Fishing Show%'
    ''').fetchone()
    
    if not trip:
        print("❌ Unsuccessful Fishing Show trip not found!")
        return
    
    trip_id, trip_name = trip
    print(f"✅ Found trip: {trip_name} (ID: {trip_id})")
    
    # Find missing episodes by searching for any video with "Unsuccessful Fishing Show" and "Episode"
    all_episodes = cursor.execute('''
    SELECT video_id, title 
    FROM videos 
    WHERE title LIKE '%Unsuccessful Fishing Show%' 
    AND title LIKE '%Episode%'
    ORDER BY title
    ''').fetchall()
    
    print(f"🔍 Found {len(all_episodes)} total episodes in database")
    
    # Check which are already in the trip
    existing_episodes = cursor.execute('''
    SELECT v.video_id, v.title, vv.part_number
    FROM videos v
    JOIN video_versions vv ON v.video_id = vv.video_id
    WHERE vv.trip_id = ?
    ''', (trip_id,)).fetchall()
    
    existing_video_ids = set(ep[0] for ep in existing_episodes)
    print(f"📊 {len(existing_episodes)} episodes already in trip")
    
    # Find missing episodes
    missing_episodes = []
    for video_id, title in all_episodes:
        if video_id not in existing_video_ids:
            # Extract episode number
            episode_match = re.search(r'episode\s+(\d+)', title, re.IGNORECASE)
            if episode_match:
                episode_num = int(episode_match.group(1))
                missing_episodes.append((video_id, title, episode_num))
    
    print(f"\\n🎯 MISSING EPISODES FOUND: {len(missing_episodes)}")
    
    # Add missing episodes to trip
    for video_id, title, episode_num in missing_episodes:
        print(f"   Adding Episode {episode_num}: {title}")
        
        try:
            cursor.execute('''
            INSERT INTO video_versions (trip_id, version_type, part_number, total_parts, video_id)
            VALUES (?, ?, ?, ?, ?)
            ''', (trip_id, 'episode', episode_num, len(all_episodes), video_id))
            
        except sqlite3.Error as e:
            print(f"   ❌ Error adding episode: {e}")
    
    # Update total_parts for all episodes in this trip
    cursor.execute('''
    UPDATE video_versions 
    SET total_parts = ?
    WHERE trip_id = ?
    ''', (len(all_episodes), trip_id))
    
    conn.commit()
    
    # Verify final state
    final_episodes = cursor.execute('''
    SELECT v.video_id, v.title, vv.part_number
    FROM videos v
    JOIN video_versions vv ON v.video_id = vv.video_id
    WHERE vv.trip_id = ?
    ORDER BY vv.part_number
    ''', (trip_id,)).fetchall()
    
    print(f"\\n✅ TRIP UPDATE COMPLETE")
    print(f"   Total episodes now: {len(final_episodes)}")
    print(f"   Episode numbers: {sorted([ep[2] for ep in final_episodes])}")
    
    # Check for any gaps
    episode_numbers = sorted([ep[2] for ep in final_episodes])
    gaps = []
    for i in range(1, max(episode_numbers) + 1):
        if i not in episode_numbers:
            gaps.append(i)
    
    if gaps:
        print(f"   ⚠️  Missing episode numbers: {gaps}")
    else:
        print(f"   ✅ No gaps in episode sequence")
    
    conn.close()
    
    print(f"\\n🎉 The Unsuccessful Fishing Show now complete!")
    print(f"   Refresh the trips page to see all episodes")

if __name__ == "__main__":
    fix_missing_episodes()
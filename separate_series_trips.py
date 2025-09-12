#!/usr/bin/env python3
"""
Separate episodic series from multi-day trips.
Updates database to distinguish between the two types.
"""

import sqlite3

def separate_series_and_trips():
    """Add series_type field and categorize existing trips"""
    
    conn = sqlite3.connect('posa_wiki.db')
    cursor = conn.cursor()
    
    print("🔧 SEPARATING SERIES FROM TRIPS")
    print("=" * 40)
    
    # Add series_type column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE trips ADD COLUMN series_type VARCHAR DEFAULT "trip"')
        print("✅ Added series_type column to trips table")
    except sqlite3.Error:
        print("ℹ️  series_type column already exists")
    
    # Get all current trips and categorize them
    trips = cursor.execute('SELECT trip_id, trip_name, description FROM trips').fetchall()
    
    print(f"\\n📊 Categorizing {len(trips)} entries:")
    
    series_count = 0
    trip_count = 0
    
    for trip_id, trip_name, description in trips:
        # Determine if it's a series or trip based on patterns
        is_series = False
        
        # Series indicators
        series_keywords = [
            'fishing show', 'episode', 'show', 'series'
        ]
        
        # Trip indicators  
        trip_keywords = [
            'wilderness', 'adventure', 'camping', 'canoe', 'night', 'day'
        ]
        
        trip_name_lower = trip_name.lower()
        
        # Check for series patterns
        if any(keyword in trip_name_lower for keyword in series_keywords):
            is_series = True
        
        # Check version type in videos
        version_types = cursor.execute('''
        SELECT DISTINCT version_type FROM video_versions WHERE trip_id = ?
        ''', (trip_id,)).fetchall()
        
        if any('episode' in vt[0] for vt in version_types):
            is_series = True
        
        # Update the categorization
        if is_series:
            cursor.execute('UPDATE trips SET series_type = ? WHERE trip_id = ?', ('series', trip_id))
            print(f"   📺 SERIES: {trip_name}")
            series_count += 1
        else:
            cursor.execute('UPDATE trips SET series_type = ? WHERE trip_id = ?', ('trip', trip_id))
            print(f"   🏕️  TRIP: {trip_name}")
            trip_count += 1
    
    conn.commit()
    
    print(f"\\n📈 CATEGORIZATION COMPLETE:")
    print(f"   Series: {series_count}")
    print(f"   Trips: {trip_count}")
    
    # Show the breakdown
    print(f"\\n🎬 SERIES:")
    series = cursor.execute('''
    SELECT trip_name, COUNT(vv.video_id) as video_count
    FROM trips t
    LEFT JOIN video_versions vv ON t.trip_id = vv.trip_id
    WHERE t.series_type = 'series'
    GROUP BY t.trip_id
    ORDER BY video_count DESC
    ''').fetchall()
    
    for name, count in series:
        print(f"   • {name}: {count} episodes")
    
    print(f"\\n🏕️  TRIPS:")
    trips = cursor.execute('''
    SELECT trip_name, COUNT(vv.video_id) as video_count
    FROM trips t
    LEFT JOIN video_versions vv ON t.trip_id = vv.trip_id
    WHERE t.series_type = 'trip'
    GROUP BY t.trip_id
    ORDER BY video_count DESC
    ''').fetchall()
    
    for name, count in trips:
        print(f"   • {name}: {count} parts")
    
    conn.close()
    
    print(f"\\n🎉 Ready to create separate Series and Trips pages!")

if __name__ == "__main__":
    separate_series_and_trips()
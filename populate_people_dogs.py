#!/usr/bin/env python3
"""
Populate the people/dogs junction tables by analyzing validated tags in videos.
This connects videos to the people and dogs that appear in them.
"""

import sqlite3
import json
from datetime import datetime

def populate_people_dogs_junctions():
    """Populate video_people and video_dogs junction tables using description mining results"""
    
    print("👥 POPULATING PEOPLE/DOGS JUNCTION TABLES FROM DESCRIPTION MINING")
    print("=" * 50)
    
    conn = sqlite3.connect('posa_wiki.db')
    cursor = conn.cursor()
    
    # Map mining results to database IDs
    # Description mining uses these keys, map to DB person_id
    people_mapping = {
        "matthew": 1,      # Matthew Posa
        "lucas": 3,        # Lucas  
        "funk": 2,         # Funk
        "erin": 4,         # Erin
        "jake": 5,         # Jake
        "ken": 6,          # Ken
        # Family members - we'll need to add these to people table
        "mom": None,       # Need to add to people table
        "dad": None,       # Need to add to people table  
        "brother": None,   # Need to add to people table
    }
    
    dogs_mapping = {
        "monty": 1,        # Monty
        "rueger": 2,       # Rueger
        # Note: "frodo" mentioned in mining script but not in our videos
    }
    
    # First, add family members to people table if they don't exist
    family_members = [
        ("Matthew's Mom", "mom", "Matthew's mother, appears in some videos"),
        ("Matthew's Dad", "dad", "Matthew's father, goes on BWCA canoe trips"),  
        ("Matthew's Brother", "brother", "Matthew's brother, joins family adventures")
    ]
    
    for canonical_name, key, bio in family_members:
        cursor.execute('SELECT person_id FROM people WHERE canonical_name = ?', (canonical_name,))
        if not cursor.fetchone():
            cursor.execute('''
            INSERT INTO people (canonical_name, aliases, bio)
            VALUES (?, ?, ?)
            ''', (canonical_name, json.dumps([key]), bio))
            person_id = cursor.lastrowid
            people_mapping[key] = person_id
            print(f"  ➕ Added {canonical_name} as person_id {person_id}")
        else:
            # Get the existing ID
            cursor.execute('SELECT person_id FROM people WHERE canonical_name = ?', (canonical_name,))
            people_mapping[key] = cursor.fetchone()[0]
    
    conn.commit()
    
    # Load description mining results instead of validated tags
    try:
        with open('video_description_mining_results.json', 'r') as f:
            mining_results = json.load(f)
    except FileNotFoundError:
        print("❌ Description mining results not found. Run mine_video_descriptions.py first.")
        return
    
    high_confidence_results = mining_results['high_confidence']
    
    print(f"📊 Processing {len(high_confidence_results)} videos with high confidence mining results...")
    
    people_connections = 0
    dog_connections = 0
    
    # Process high confidence results from description mining
    for video_id, title, entities in high_confidence_results:
        for entity_key, entity_type, context in entities:
            
            # Handle people
            if entity_type == 'person' and entity_key in people_mapping:
                person_id = people_mapping[entity_key]
                if person_id is not None:
                    # Insert into video_people (avoid duplicates)
                    cursor.execute('''
                    INSERT OR IGNORE INTO video_people (video_id, person_id)
                    VALUES (?, ?)
                    ''', (video_id, person_id))
                    
                    if cursor.rowcount > 0:
                        people_connections += 1
                        print(f"  ✅ {video_id}: Connected to {entity_key} ({context})")
            
            # Handle dogs
            elif entity_type == 'dog' and entity_key in dogs_mapping:
                dog_id = dogs_mapping[entity_key]
                # Insert into video_dogs (avoid duplicates)
                cursor.execute('''
                INSERT OR IGNORE INTO video_dogs (video_id, dog_id)
                VALUES (?, ?)
                ''', (video_id, dog_id))
                
                if cursor.rowcount > 0:
                    dog_connections += 1
                    print(f"  🐕 {video_id}: Connected to {entity_key} ({context})")
    
    conn.commit()
    
    print(f"\n📊 JUNCTION TABLE POPULATION COMPLETE!")
    print(f"   People connections: {people_connections}")
    print(f"   Dog connections: {dog_connections}")
    
    # Show summary statistics
    print(f"\n📈 SUMMARY BY PERSON/DOG:")
    
    # People stats
    print("People appearances:")
    for key, person_id in people_mapping.items():
        if person_id is not None:
            cursor.execute('SELECT COUNT(*) FROM video_people WHERE person_id = ?', (person_id,))
            count = cursor.fetchone()[0]
            # Get the actual name from database
            cursor.execute('SELECT canonical_name FROM people WHERE person_id = ?', (person_id,))
            db_name = cursor.fetchone()[0]
            print(f"  {db_name:20} {count:3} videos ({key})")
    
    # Dog stats  
    print("\nDog appearances:")
    for key, dog_id in dogs_mapping.items():
        cursor.execute('SELECT COUNT(*) FROM video_dogs WHERE dog_id = ?', (dog_id,))
        count = cursor.fetchone()[0]
        # Get the actual name from database
        cursor.execute('SELECT name FROM dogs WHERE dog_id = ?', (dog_id,))
        db_name = cursor.fetchone()[0]
        print(f"  {db_name:20} {count:3} videos ({key})")
    
    # Show some example video connections
    print(f"\n🎬 EXAMPLE CONNECTIONS:")
    cursor.execute('''
    SELECT v.video_id, v.title, p.canonical_name
    FROM videos v
    JOIN video_people vp ON v.video_id = vp.video_id
    JOIN people p ON vp.person_id = p.person_id
    LIMIT 5
    ''')
    
    for video_id, title, person_name in cursor.fetchall():
        print(f"  {video_id}: {title[:40]}... → {person_name}")
    
    cursor.execute('''
    SELECT v.video_id, v.title, d.name
    FROM videos v
    JOIN video_dogs vd ON v.video_id = vd.video_id  
    JOIN dogs d ON vd.dog_id = d.dog_id
    LIMIT 5
    ''')
    
    print("\nDog connections:")
    for video_id, title, dog_name in cursor.fetchall():
        print(f"  {video_id}: {title[:40]}... → {dog_name}")
    
    conn.close()
    print(f"\n🎉 People/Dogs junction tables populated successfully!")

if __name__ == "__main__":
    populate_people_dogs_junctions()
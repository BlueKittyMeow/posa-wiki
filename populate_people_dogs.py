#!/usr/bin/env python3
"""
Populate the people/dogs junction tables by analyzing validated tags in videos.
This connects videos to the people and dogs that appear in them.
"""

import sqlite3
import json
from datetime import datetime

# Mining-key -> DB id mappings.  Kept at module level so incremental tooling
# (scripts/update_catalog.py) can reuse them instead of duplicating the logic.
PEOPLE_MAPPING = {
    "matthew": 1,      # Matthew Posa
    "lucas": 3,        # Lucas
    "funk": 2,         # Funk
    "erin": 4,         # Erin
    "jake": 5,         # Jake
    "ken": 6,          # Ken
    # Family members are resolved/created by ensure_family_members()
    "mom": None,
    "dad": None,
    "brother": None,
}

DOGS_MAPPING = {
    "monty": 1,        # Monty
    "rueger": 2,       # Rueger
    "layla": 3,        # Layla
    # Note: "frodo" appears in the mining aliases but has no dogs row.
}

FAMILY_MEMBERS = [
    ("Matthew's Mom", "mom", "Matthew's mother, appears in some videos"),
    ("Matthew's Dad", "dad", "Matthew's father, goes on BWCA canoe trips"),
    ("Matthew's Brother", "brother", "Matthew's brother, joins family adventures"),
]


def ensure_family_members(cursor, people_mapping=None, verbose=True):
    """Make sure the family people rows exist; return a filled-in mapping."""
    mapping = dict(PEOPLE_MAPPING if people_mapping is None else people_mapping)

    for canonical_name, key, bio in FAMILY_MEMBERS:
        cursor.execute('SELECT person_id FROM people WHERE canonical_name = ?', (canonical_name,))
        row = cursor.fetchone()
        if row:
            mapping[key] = row[0]
        else:
            cursor.execute('''
            INSERT INTO people (canonical_name, aliases, bio)
            VALUES (?, ?, ?)
            ''', (canonical_name, json.dumps([key]), bio))
            mapping[key] = cursor.lastrowid
            if verbose:
                print(f"  ➕ Added {canonical_name} as person_id {mapping[key]}")

    return mapping


def link_entities(cursor, video_id, entities, people_mapping, dogs_mapping, verbose=True):
    """Insert video_people / video_dogs rows for one video's mined entities.

    ``entities`` is the high-confidence list produced by
    ``mine_video_descriptions.analyze_description``.  Returns
    ``(people_added, dogs_added)``.
    """
    people_added = 0
    dogs_added = 0

    for entity_key, entity_type, context in entities:
        if entity_type == 'person' and entity_key in people_mapping:
            person_id = people_mapping[entity_key]
            if person_id is None:
                continue
            cursor.execute('''
            INSERT OR IGNORE INTO video_people (video_id, person_id)
            VALUES (?, ?)
            ''', (video_id, person_id))
            if cursor.rowcount > 0:
                people_added += 1
                if verbose:
                    print(f"  ✅ {video_id}: Connected to {entity_key} ({context})")

        elif entity_type == 'dog' and entity_key in dogs_mapping:
            dog_id = dogs_mapping[entity_key]
            if dog_id is None:
                continue
            cursor.execute('''
            INSERT OR IGNORE INTO video_dogs (video_id, dog_id)
            VALUES (?, ?)
            ''', (video_id, dog_id))
            if cursor.rowcount > 0:
                dogs_added += 1
                if verbose:
                    print(f"  🐕 {video_id}: Connected to {entity_key} ({context})")

    return people_added, dogs_added


def populate_people_dogs_junctions():
    """Populate video_people and video_dogs junction tables using description mining results"""
    
    print("👥 POPULATING PEOPLE/DOGS JUNCTION TABLES FROM DESCRIPTION MINING")
    print("=" * 50)
    
    conn = sqlite3.connect('posa_wiki.db')
    cursor = conn.cursor()
    
    # Map mining results to database IDs (module-level constants above).
    dogs_mapping = dict(DOGS_MAPPING)

    # First, add family members to people table if they don't exist
    people_mapping = ensure_family_members(cursor)
    
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
        added_people, added_dogs = link_entities(
            cursor, video_id, entities, people_mapping, dogs_mapping
        )
        people_connections += added_people
        dog_connections += added_dogs
    
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
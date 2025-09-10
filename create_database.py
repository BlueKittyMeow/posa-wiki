#!/usr/bin/env python3
"""
Create SQLite database from schema.md for Posa Wiki project.
Implements the complete database structure with all tables and relationships.
"""

import sqlite3
import json
from datetime import datetime

def create_database():
    """Create the complete database structure"""
    
    # Connect to database (creates if doesn't exist)
    conn = sqlite3.connect('posa_wiki.db')
    cursor = conn.cursor()
    
    print("🗃️  Creating Posa Wiki database structure...")
    
    # Core videos table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS videos (
        video_id VARCHAR PRIMARY KEY,
        title TEXT NOT NULL,
        upload_date DATE,
        duration VARCHAR,
        view_count INTEGER,
        description TEXT,
        thumbnail_url VARCHAR,
        thumbnail_local_path VARCHAR,
        number_of_nights INTEGER,
        season VARCHAR,
        weather_conditions VARCHAR,
        series_notes TEXT,
        youtube_tags JSON,
        validated_tags JSON,
        unvalidated_tags JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Authority tables
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS people (
        person_id INTEGER PRIMARY KEY,
        canonical_name VARCHAR NOT NULL,
        youtube_handle VARCHAR,
        youtube_url VARCHAR,
        aliases JSON,
        bio TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS dogs (
        dog_id INTEGER PRIMARY KEY,
        name VARCHAR NOT NULL,
        birth_date DATE,
        breed_primary VARCHAR,
        breed_secondary VARCHAR,
        breed_detail VARCHAR,
        breed_source VARCHAR,
        color VARCHAR,
        description TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS locations (
        location_id INTEGER PRIMARY KEY,
        main_location VARCHAR NOT NULL,
        specific_location VARCHAR,
        coordinates VARCHAR,
        location_type VARCHAR,
        description TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS series (
        series_id INTEGER PRIMARY KEY,
        name VARCHAR NOT NULL,
        description TEXT,
        is_episodic BOOLEAN DEFAULT FALSE,
        series_type VARCHAR DEFAULT 'activity',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS trips (
        trip_id INTEGER PRIMARY KEY,
        trip_name VARCHAR NOT NULL,
        start_date DATE,
        end_date DATE,
        description TEXT,
        location_primary INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (location_primary) REFERENCES locations(location_id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS video_versions (
        version_id INTEGER PRIMARY KEY,
        trip_id INTEGER,
        version_type VARCHAR,
        part_number INTEGER,
        total_parts INTEGER,
        video_id VARCHAR,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (trip_id) REFERENCES trips(trip_id),
        FOREIGN KEY (video_id) REFERENCES videos(video_id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS posa_references (
        reference_id INTEGER PRIMARY KEY,
        name VARCHAR NOT NULL,
        type VARCHAR,
        description TEXT,
        first_appearance_video_id VARCHAR,
        first_appearance_timestamp VARCHAR,
        category VARCHAR,
        person_id INTEGER,
        context TEXT,
        frequency VARCHAR,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (first_appearance_video_id) REFERENCES videos(video_id),
        FOREIGN KEY (person_id) REFERENCES people(person_id)
    )
    ''')
    
    # Relationship tables
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS video_people (
        video_id VARCHAR,
        person_id INTEGER,
        role VARCHAR,
        notes TEXT,
        PRIMARY KEY (video_id, person_id),
        FOREIGN KEY (video_id) REFERENCES videos(video_id),
        FOREIGN KEY (person_id) REFERENCES people(person_id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS video_dogs (
        video_id VARCHAR,
        dog_id INTEGER,
        role VARCHAR,
        notes TEXT,
        PRIMARY KEY (video_id, dog_id),
        FOREIGN KEY (video_id) REFERENCES videos(video_id),
        FOREIGN KEY (dog_id) REFERENCES dogs(dog_id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS video_locations (
        video_id VARCHAR,
        location_id INTEGER,
        role VARCHAR,
        notes TEXT,
        PRIMARY KEY (video_id, location_id),
        FOREIGN KEY (video_id) REFERENCES videos(video_id),
        FOREIGN KEY (location_id) REFERENCES locations(location_id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS video_series (
        video_id VARCHAR,
        series_id INTEGER,
        episode_number INTEGER,
        trip_id INTEGER,
        notes TEXT,
        PRIMARY KEY (video_id, series_id),
        FOREIGN KEY (video_id) REFERENCES videos(video_id),
        FOREIGN KEY (series_id) REFERENCES series(series_id),
        FOREIGN KEY (trip_id) REFERENCES trips(trip_id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS video_references (
        video_id VARCHAR,
        reference_id INTEGER,
        timestamp VARCHAR,
        context TEXT,
        is_first_appearance BOOLEAN DEFAULT FALSE,
        notes TEXT,
        PRIMARY KEY (video_id, reference_id),
        FOREIGN KEY (video_id) REFERENCES videos(video_id),
        FOREIGN KEY (reference_id) REFERENCES posa_references(reference_id)
    )
    ''')
    
    # Authority tables
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS breed_authority (
        breed_id INTEGER PRIMARY KEY,
        breed_name VARCHAR NOT NULL,
        breed_group VARCHAR,
        akc_recognized BOOLEAN,
        source VARCHAR,
        notes TEXT
    )
    ''')
    
    # People-Dog relationships  
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS people_dogs (
        person_id INTEGER,
        dog_id INTEGER,
        relationship_type VARCHAR,
        start_date DATE,
        end_date DATE,
        notes TEXT,
        is_reciprocal BOOLEAN DEFAULT TRUE,
        PRIMARY KEY (person_id, dog_id),
        FOREIGN KEY (person_id) REFERENCES people(person_id),
        FOREIGN KEY (dog_id) REFERENCES dogs(dog_id)
    )
    ''')
    
    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_videos_upload_date ON videos(upload_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_videos_duration ON videos(duration)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_people_video ON video_people(video_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_locations_video ON video_locations(video_id)')
    
    print("✅ Database structure created successfully!")
    
    # Insert some initial data
    print("📊 Inserting seed data...")
    
    # Insert people
    people_data = [
        (1, 'Matthew Posa', '@MatthewPosa', 'https://youtube.com/@MatthewPosa', 
         '["Captain Teeny Trout", "Teeny Trout"]', 'Primary creator of outdoor adventure videos', None),
        (2, 'Funk', None, None, '["Erin"]', 'Partner and regular camping companion', None),
        (3, 'Lucas', '@LucasAndLayla', 'https://youtube.com/@LucasAndLayla', 
         '[]', 'Friend and fellow outdoor content creator', None),
        (4, 'Erin', None, None, '[]', 'Friend (different from Funk, also named Erin)', None)
    ]
    
    cursor.executemany('''
    INSERT OR REPLACE INTO people 
    (person_id, canonical_name, youtube_handle, youtube_url, aliases, bio, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', people_data)
    
    # Insert dogs
    dogs_data = [
        (1, 'Monty', None, 'Rough Collie', None, 'Rough', 'AKC', 'Sable', 
         'Matthew\'s primary adventure companion', None),
        (2, 'Rueger', None, 'Mixed Breed', None, None, 'mixed', None,
         'Matthew\'s adventure companion, mixed breed', None),
        (3, 'Layla', None, 'English Shepherd', None, None, 'UKC', None,
         'Lucas\'s companion, English Shepherd breed', None)
    ]
    
    cursor.executemany('''
    INSERT OR REPLACE INTO dogs
    (dog_id, name, birth_date, breed_primary, breed_secondary, breed_detail, 
     breed_source, color, description, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', dogs_data)
    
    # Insert breed authority
    breed_data = [
        (1, 'Rough Collie', 'Herding', True, 'AKC', 'Long-haired herding breed'),
        (2, 'English Shepherd', 'Herding', False, 'UKC', 'American herding breed, UKC recognized'),
        (3, 'Mixed Breed', None, False, 'mixed', 'Non-purebred dogs')
    ]
    
    cursor.executemany('''
    INSERT OR REPLACE INTO breed_authority
    (breed_id, breed_name, breed_group, akc_recognized, source, notes)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', breed_data)
    
    # Insert some example references
    references_data = [
        (1, 'Blue Sklies', 'posaism', 'Intentional mispronunciation of "blue skies"', 
         None, None, 'phrase', 1, 'Weather commentary signature', 'recurring', None),
        (2, 'Salt Wisdom', 'posaism', 'Not too much salt, not too little salt, just the right amount of salt',
         None, None, 'phrase', 1, 'Cooking/seasoning philosophy', 'recurring', None),
        (3, 'Fishing Philosophy', 'posaism', 'Where there\'s downed trees there\'s fish and where there\'s fish you\'ll catch \'em',
         None, None, 'phrase', 1, 'Fishing wisdom with variations', 'recurring', None)
    ]
    
    cursor.executemany('''
    INSERT OR REPLACE INTO posa_references
    (reference_id, name, type, description, first_appearance_video_id, 
     first_appearance_timestamp, category, person_id, context, frequency, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', references_data)
    
    # Insert example series
    series_data = [
        # Activity series
        (1, 'Canoe Camping', 'Paddling and canoe-based adventures', False, 'activity'),
        (2, 'Winter Camping', 'Cold weather camping adventures', False, 'activity'),
        (3, 'Spring Camping', 'Spring season camping adventures', False, 'activity'),
        (4, 'Fall Camping', 'Autumn camping adventures', False, 'activity'),
        (5, 'Backpacking', 'Multi-day hiking adventures', False, 'activity'),
        
        # Location series
        (6, 'Boundary Waters', 'Boundary Waters Canoe Area adventures', False, 'location'),
        (7, 'Isle Royale', 'Isle Royale National Park adventures', False, 'location'),
        (8, 'Michigan Adventures', 'Michigan-based outdoor content', False, 'location'),
        
        # Content series
        (9, 'Community Content', 'Giveaways, unboxing, and channel updates', False, 'content'),
        (10, 'Unsuccessful Fishing Show', 'Episodic fishing adventure series', True, 'content'),
        (11, 'Special Occasions', 'Birthdays, holidays, and celebrations', False, 'special')
    ]
    
    cursor.executemany('''
    INSERT OR REPLACE INTO series
    (series_id, name, description, is_episodic, series_type)
    VALUES (?, ?, ?, ?, ?)
    ''', series_data)
    
    conn.commit()
    conn.close()
    
    print("🎉 Posa Wiki database created successfully!")
    print("   Database file: posa_wiki.db")
    print("   Tables created: 15")
    print("   Seed data inserted: People, Dogs, Breeds, References, Series")
    print("")
    print("🚀 Ready for video data import and tag validation!")

if __name__ == "__main__":
    create_database()
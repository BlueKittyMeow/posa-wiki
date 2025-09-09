# Matthew Posa YouTube Catalog - Database Schema

## Core Tables

### videos
Primary table for video metadata from YouTube API
- `video_id` (VARCHAR, PRIMARY KEY) - YouTube video ID
- `title` (TEXT) - Video title
- `upload_date` (DATE) - When video was published
- `duration` (VARCHAR) - ISO 8601 duration (PT4M19S)
- `view_count` (INTEGER) - View count at time of scraping
- `description` (TEXT) - Full video description
- `thumbnail_url` (VARCHAR) - YouTube thumbnail URL (high quality)
- `thumbnail_local_path` (VARCHAR, NULLABLE) - Local file path if downloaded
- `created_at` (TIMESTAMP) - When record was created
- `updated_at` (TIMESTAMP) - When record was last updated

### Manual Curation Fields (added by human review)
- `number_of_nights` (INTEGER, NULLABLE) - Extracted or manually entered
- `season` (VARCHAR, NULLABLE) - winter, spring, summer, fall
- `weather_conditions` (VARCHAR, NULLABLE) - sunny, rainy, stormy, etc.
- `series_notes` (TEXT, NULLABLE) - Manual series categorization notes

### YouTube Tags (NEW!)
- `youtube_tags` (JSON) - Array of tags from YouTube API
  - Example: ["moose encounter", "boundary waters canoe area", "bwca", "winter camping"]
  - These are creator-assigned and could be great for authority control validation

## Authority Tables

### people
- `person_id` (INTEGER, PRIMARY KEY)
- `canonical_name` (VARCHAR) - "Matthew Posa", "Lucas"
- `youtube_handle` (VARCHAR, NULLABLE) - "@MatthewPosa", "@LucasAndLayla"
- `youtube_url` (VARCHAR, NULLABLE) - Full YouTube channel URL
- `aliases` (JSON) - Array of alternative names ["Captain Teeny Trout", "Teeny Trout"]
- `bio` (TEXT, NULLABLE) - Brief description
- `notes` (TEXT, NULLABLE) - Additional curator notes
- `created_at` (TIMESTAMP)

### dogs
- `dog_id` (INTEGER, PRIMARY KEY)
- `name` (VARCHAR) - "Monty", "Rueger"
- `birth_date` (DATE, NULLABLE) - For age calculation
- `breed_primary` (VARCHAR, NULLABLE) - AKC recognized breed or "Mixed"
- `breed_secondary` (VARCHAR, NULLABLE) - For mixed breeds, second breed
- `breed_detail` (VARCHAR, NULLABLE) - "rough", "smooth", specific variety
- `breed_source` (VARCHAR, NULLABLE) - "AKC", "estimate", "unknown"
- `color` (VARCHAR, NULLABLE) - "Sable", "Tri-color", etc.
- `description` (TEXT, NULLABLE)
- `notes` (TEXT, NULLABLE)
- `created_at` (TIMESTAMP)

### locations
- `location_id` (INTEGER, PRIMARY KEY)
- `main_location` (VARCHAR) - "Boundary Waters Canoe Area", "Isle Royale"
- `specific_location` (VARCHAR, NULLABLE) - "Fat Lake", specific campsites
- `coordinates` (VARCHAR, NULLABLE) - lat,lng if available
- `location_type` (VARCHAR) - "wilderness_area", "campground", "lake", "trail"
- `description` (TEXT, NULLABLE)
- `notes` (TEXT, NULLABLE)
- `created_at` (TIMESTAMP)

### series
- `series_id` (INTEGER, PRIMARY KEY)
- `name` (VARCHAR) - "Boundary Waters Adventures", "Winter Camping"
- `description` (TEXT)
- `created_at` (TIMESTAMP)

### trips (NEW - for multi-part video linking)
- `trip_id` (INTEGER, PRIMARY KEY)
- `trip_name` (VARCHAR) - "10 Day Boundary Waters Solo - October 2019"
- `start_date` (DATE, NULLABLE) - actual trip start date
- `end_date` (DATE, NULLABLE) - actual trip end date
- `description` (TEXT)
- `location_primary` (INTEGER, FK to locations)
- `created_at` (TIMESTAMP)

### video_versions (NEW - for short/long cuts)
- `version_id` (INTEGER, PRIMARY KEY)
- `trip_id` (INTEGER, FK to trips)
- `version_type` (VARCHAR) - "short", "long", "highlight"
- `part_number` (INTEGER, NULLABLE) - 1, 2, 3 for multi-part
- `total_parts` (INTEGER, NULLABLE) - 3 if it's part "2 of 3"
- `video_id` (VARCHAR, FK to videos)
- `created_at` (TIMESTAMP)

### references (Posaisms, songs, characters, etc.)
- `reference_id` (INTEGER, PRIMARY KEY)
- `name` (VARCHAR) - "Blue Sklies", "Ronaldo The Unsplittable", "Chopping Wood"
- `type` (VARCHAR) - "posaism", "character", "song", "location_nickname", "running_gag"
- `description` (TEXT) - What this reference is about
- `first_appearance_video_id` (VARCHAR, FK) - First known canonical appearance
- `first_appearance_timestamp` (VARCHAR, NULLABLE) - Time in video (e.g., "2:34")
- `category` (VARCHAR, NULLABLE) - "phrase", "object", "song", "nickname"
- `person_id` (INTEGER, FK, NULLABLE) - Who created/uses this (usually Posa)
- `context` (TEXT, NULLABLE) - Background story or context
- `frequency` (VARCHAR, NULLABLE) - "recurring", "occasional", "one-time"
- `notes` (TEXT, NULLABLE)
- `created_at` (TIMESTAMP)

**Note**: Each reference gets ONE page listing all video appearances + canonical first use

## Relationship Tables

### video_people (Many-to-Many)
- `video_id` (VARCHAR, FOREIGN KEY)
- `person_id` (INTEGER, FOREIGN KEY)
- `role` (VARCHAR) - "primary", "companion", "mentioned"
- `notes` (TEXT, NULLABLE)

### video_dogs (Many-to-Many)
- `video_id` (VARCHAR, FOREIGN KEY)
- `dog_id` (INTEGER, FOREIGN KEY)
- `role` (VARCHAR) - "companion", "featured", "mentioned"
- `notes` (TEXT, NULLABLE)

### video_locations (Many-to-Many)
- `video_id` (VARCHAR, FOREIGN KEY)
- `location_id` (INTEGER, FOREIGN KEY)
- `role` (VARCHAR) - "primary", "visited", "mentioned"
- `notes` (TEXT, NULLABLE)

### video_series (Many-to-Many)
- `video_id` (VARCHAR, FOREIGN KEY)
- `series_id` (INTEGER, FOREIGN KEY)
- `episode_number` (INTEGER, NULLABLE) - If applicable
- `notes` (TEXT, NULLABLE)

### video_references (Many-to-Many)
- `video_id` (VARCHAR, FOREIGN KEY)
- `reference_id` (INTEGER, FOREIGN KEY)
- `timestamp` (VARCHAR, NULLABLE) - Where in video it appears (e.g., "12:34")
- `context` (TEXT, NULLABLE) - How it's used in this specific video
- `is_first_appearance` (BOOLEAN DEFAULT FALSE) - Mark the original appearance
- `notes` (TEXT, NULLABLE)

### People-Dog Relationships
- `person_id` (INTEGER, FOREIGN KEY)
- `dog_id` (INTEGER, FOREIGN KEY)
- `relationship_type` (VARCHAR) - "owner", "caretaker", "trainer"
- `start_date` (DATE, NULLABLE)
- `end_date` (DATE, NULLABLE)
- `notes` (TEXT, NULLABLE)
- `is_reciprocal` (BOOLEAN DEFAULT TRUE) - Auto-create inverse relationship

### Dog-Dog Relationships
- `dog_id_1` (INTEGER, FOREIGN KEY)
- `dog_id_2` (INTEGER, FOREIGN KEY)
- `relationship_type` (VARCHAR) - "brothers", "siblings", "companions", "rivals"
- `relationship_detail` (TEXT, NULLABLE) - "not biological siblings but live together"
- `start_date` (DATE, NULLABLE)
- `end_date` (DATE, NULLABLE)
- `notes` (TEXT, NULLABLE)
- `is_reciprocal` (BOOLEAN DEFAULT TRUE) - Auto-create inverse (Rueger↔Monty)

### People-People Relationships (FOAF)
- `person_id` (INTEGER, FOREIGN KEY)
- `related_person_id` (INTEGER, FOREIGN KEY)
- `relationship_type` (VARCHAR) - "friend", "family", "frequent_companion"
- `notes` (TEXT, NULLABLE)
- `is_reciprocal` (BOOLEAN DEFAULT TRUE) - Auto-create inverse relationship

## Indexes for Performance
- `idx_videos_upload_date` ON videos(upload_date)
- `idx_videos_duration` ON videos(duration)
- `idx_video_people_video` ON video_people(video_id)
- `idx_video_locations_video` ON video_locations(video_id)

## Authority Tables

### breed_authority
- `breed_id` (INTEGER, PRIMARY KEY)
- `breed_name` (VARCHAR) - "Rough Collie", "Labrador Retriever"
- `breed_group` (VARCHAR) - "Herding", "Sporting", "Working"
- `akc_recognized` (BOOLEAN) - Official AKC breed status
- `source` (VARCHAR) - "AKC", "UKC", "mixed"
- `notes` (TEXT, NULLABLE)

## Reciprocal Relationship Handling
- **`is_reciprocal` flag**: When TRUE, automatically creates inverse relationship
- **Database triggers**: Auto-insert reciprocal records on INSERT/UPDATE
- **Relationship mapping**: 
  - "owner" ↔ "pet_of" 
  - "friend" ↔ "friend"
  - "brothers" ↔ "brothers"
- **Constraint**: Prevent duplicate reciprocal pairs with CHECK constraints

## Notes
- JSON fields store arrays for flexible data (youtube_tags, aliases)
- All relationship tables include notes for contextual information
- Nullable fields allow for incomplete data during manual curation process
- Foreign key constraints maintain data integrity
- Timestamps track when records were created/updated for audit trail
- Breed authority ensures consistent breed classification with AKC standards
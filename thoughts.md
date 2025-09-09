# Matthew Posa YouTube Cataloging Project

## Why This Project is Perfect

**The Perfect Storm of Skills:**
- **YouTube Data API scraping** - shows technical web development skills (JSON/API handling)
- **Custom metadata schema design** - core library science skill
- **Authority control system** - handling "Captain Teeny Trout"/"Lucas" variants
- **Cross-channel relationship mapping** - cataloging the "Posaverse" 
- **Process documentation** - shows communication skills and systematic thinking

## Manageable 3-month timeline:
1. **Month 1**: API scraping tool + basic database schema
2. **Month 2**: Web interface for cataloging + authority records
3. **Month 3**: Search/browse interface + documentation/blog posts

## Natural blog post progression:
- "Why existing tools failed me (World Anvil, MediaWiki, etc.)"
- "Building a YouTube scraper with Python"
- "Designing metadata for unstructured content"
- "Authority control for informal names and places"
- "Lessons learned from cataloging 200+ camping videos"

## Technical stack suggestion:
- Python for YouTube Data API scraping
- SQLite/PostgreSQL for data storage
- Simple web interface (Flask/Django or even static HTML/JS)
- Export capabilities (JSON, CSV, maybe Dublin Core for library street cred)

## Database Schema Ideas

### Core Video Table
- video_id (YouTube ID)
- title
- upload_date
- duration
- view_count (at time of scraping)
- description (cleaned/processed)
- raw_description (original from YouTube)
- thumbnail_url (YouTube URL)
- thumbnail_local_path (optional, if downloaded)
- season/time_of_year (manual entry)
- number_of_nights (extracted from title/description when possible, null otherwise)
- series_manual_override (for human validation)

### Authority Tables
- **People**: person_id, canonical_name, aliases, bio, notes
- **Dogs**: dog_id, name, dob/age, breed, description, notes
- **Locations**: location_id, main_location (Boundary Waters), specific_location (Fat Lake), coordinates, description, notes
- **Series**: series_id, name, description (canoe camping, winter camping, etc.)
- **Catchphrases**: phrase_id, text, first_appearance_video_id

### Relationship Tables
- **Pet Ownership**: person_id, dog_id, relationship_type (owner, caretaker), notes
- **Person Relationships (FOAF)**: person_id, related_person_id, relationship_type (friend, family), notes

### Junction Tables
- video_people (many-to-many)
- video_locations (many-to-many) 
- video_catchphrases (many-to-many)
- video_dogs (many-to-many - different dogs appear in different videos)
- video_series (many-to-many - videos can belong to multiple series)

### Manual Metadata (added by watching)
- Activities, gear used, weather, songs, special moments

## Thumbnail Storage Strategy
- Store thumbnail URLs from YouTube API (don't download initially)
- Optional local download later for specific videos
- Database stores YouTube thumbnail URLs + local path if downloaded

## Description Processing
- Extract gear lists automatically (pattern recognition)
- Store cleaned description separately from raw
- Potentially create gear authority table later

## Initial Scraping Target Fields
**YouTube API data to collect:**
- video_id
- title  
- upload_date
- duration
- view_count
- description (raw)
- thumbnail URLs (multiple sizes available)

**Processing during scrape:**
- number_of_nights: regex search in title/description for patterns like "3 nights", "overnight", etc.
- cleaned_description: remove gear lists, extract just the trip narrative

**Manual entry later:**
- People, dogs, locations, series, catchphrases (all require human validation)
- Seasonal info, weather, activities

## Project Story
This tells a great story: frustrated user → technical solution → systematic documentation.
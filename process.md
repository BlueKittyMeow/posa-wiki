# Matthew Posa YouTube Cataloging Project - Process Documentation

## Project Goal
Create a personal cataloging system for Matthew Posa's camping YouTube videos to solve the problem of finding specific episodes in an unstructured content library.

## Current Status: Initial Setup Phase

### Phase 1: Foundation Setup
**Current Step**: Setting up YouTube Data API and basic scraping infrastructure

#### Steps Completed:
- ✅ Project planning and database schema design
- ✅ Identified core metadata fields for scraping
- ✅ Designed authority control strategy

#### Currently Working On:
- 🔄 Full channel scraping (339 videos total)
- 🔄 Database implementation with seed data
- 🔄 Pattern extraction for nights/locations/people

#### Completed:
- ✅ YouTube Data API credential setup
- ✅ Data storage format decision (JSON → Database)
- ✅ Database schema with relationships (including dog-dog relationships)
- ✅ Test scrape of 10 oldest videos
- ✅ Authority record planning (Matthew, Lucas/Teeny Trout, Monty, Rueger)

#### Next Steps:
- Implement SQLite database with schema
- Build full channel scraper (all 339 videos)
- Create pattern extraction for automated metadata
- Populate authority records with seed data

## Technical Decisions Made

### Database Schema Approach
- **Core principle**: Separate automated scraping from manual curation
- **Authority control**: Canonical names with aliases for people, dogs, locations
- **Relationships**: FOAF-style connections between people and pet ownership tracking
- **Null-friendly**: Allow missing data for manual validation later

### Data Storage Strategy (TBD)
**Options under consideration:**
- **JSON files**: Good for initial scraping, preserves API structure, easy to inspect
- **CSV**: Simple, good for spreadsheet validation, but doesn't handle complex relationships well
- **Direct to SQLite**: Clean, but harder to inspect raw data and debug extraction issues

**Recommendation**: Start with JSON for raw scrapes, then process into database

### Test Scraping Strategy
- Start with **10 oldest videos** to test on simpler, earlier content
- Validate API response structure and data quality
- Test number-of-nights extraction patterns
- Check thumbnail URL accessibility

## Relationship Schema Additions Needed

### People-Dogs Relationships
```
pet_ownership table:
- person_id (FK)
- dog_id (FK) 
- relationship_type (owner, caretaker, etc.)
- notes
```

### People-People Relationships (FOAF)
```
person_relationships table:
- person_id (FK)
- related_person_id (FK)
- relationship_type (friend, family, etc.)
- notes
```

## Questions to Resolve
1. **API Rate Limits**: How many requests per day? Batch size?
2. **Data Validation**: Manual review process for extracted nights/locations?
3. **Storage Location**: Local SQLite vs cloud database for final system?

---
*Last updated: [Current Date]*
*Next milestone: Complete API setup and first test scrape*
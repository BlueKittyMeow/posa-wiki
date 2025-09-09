# Posa Wiki

A wiki-style catalog system for Matthew Posa's outdoor adventure videos, featuring tag authority control and reference tracking.

## Project Overview

This system creates a structured database and wiki interface for cataloging YouTube outdoor adventure content, with special focus on:
- **Tag Authority System**: Canonical tag mapping with alias resolution
- **Posaism Tracking**: References, catchphrases, and recurring elements
- **Multi-creator Support**: Matthew Posa (@MatthewPosa) and Lucas (@LucasAndLayla)
- **Rich Metadata**: Locations, people, dogs, trips, and series organization

## Current Status

### ✅ Completed
- Database schema design (`schema.md`)
- Tag authority seed system (`tag_authority_seed.py`)
- Initial data scraping for 277 videos
- Reference/Posaism tracking structure

### 🚧 In Progress
- Git repository setup
- Expanded data collection for better tag coverage
- SQLite database implementation

### 📋 Roadmap
1. **Phase 1**: Read-only wiki pages from database
2. **Phase 2**: Inline editing capabilities  
3. **Phase 3**: Full admin interface for curation

## Data Sources
- YouTube API for video metadata
- Manual curation for references and relationships
- Tag authority system for consistent categorization

## Key Features
- **Wiki-style Interface**: Database-driven pages with cross-linking
- **Tag Validation**: Authority-based tag normalization
- **Reference Tracking**: First appearances and frequency analysis
- **Multi-format Export**: JSON, SQL, CSV support planned

## Technology Stack
- **Database**: SQLite (dev) → PostgreSQL (production)
- **Backend**: Python with YouTube API integration
- **Frontend**: Web interface for wiki browsing
- **Version Control**: Git with GitHub hosting
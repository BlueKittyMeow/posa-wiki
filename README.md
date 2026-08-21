# 🏕️ Posa Wiki

A fully functional Flask web application for browsing Matthew Posa's outdoor adventure videos with dark hacker girl aesthetic and comprehensive metadata.

**Status**: Phase 2B step 1 complete (`2b-dev` branch). See `docs/phase-2b.md` and `docs/keeping-current.md` for the current plan and up-to-date project state.

**Live deployment**: https://posa-wiki.bluekittymeow.com, running on Factotum (Pi 5 home server).

## 🚀 Live Features

**Running Flask App**: Start with `python app.py` on http://localhost:5001

- **358 Videos** with full YouTube metadata and thumbnails
- **Three Theme Options**:
  - 🌈 Fairyfloss (dark purple/pink/mint - default)
  - 💼 Professional (blue corporate aesthetic)
  - 📚 Academia (warm paper/parchment/leather)
- **DaddyTimeMono Font** with custom programming aesthetic
- **Fully Responsive**: Desktop, tablet, and mobile optimized
- **Smart Navigation**: Browse by date, people, dogs, series, trips
- **Full-text Search** across titles and descriptions
- **Sortable Video Lists** by date, title, duration
- **Rich Relationship Data**: People and dogs linked to their videos

## 📊 Current Database

- **358 videos** from Matthew Posa's channel
- **9 people** (Matthew, family, collaborators)  
- **3 dogs** (Monty, Rueger, etc.)
- **13 trips/series** with episodic organization
- **Tag authority system** with validation pipeline

## 🎯 Key Pages

- **Home** (`/`) - Recent videos, date nav, search
- **All Videos** (`/videos`) - Sortable list with thumbnails  
- **People** (`/people`) - Adventure crew directory
- **Dogs** (`/dogs`) - Four-legged cast members
- **Series** (`/series`) - Episodic content like "Unsuccessful Fishing Show"
- **Trips** (`/trips`) - Multi-day adventures
- **Date View** (`/date/YYYY-MM-DD`) - Videos from a specific date
- **Search** (`/search?q=term`) - Full-text search results
- **Video Details** (`/video/ID`) - Full metadata and relationships

## 📁 Project Structure

```
├── app.py                 # Flask application
├── templates/             # Jinja2 templates
│   ├── base.html         # Base template with sidebar
│   ├── index.html        # Landing page
│   ├── video_list.html   # Sortable video listing
│   ├── video_detail.html # Individual video page
│   ├── people_list.html  # People directory
│   ├── person_detail.html # Person profile with videos
│   ├── date_view.html    # Videos by date
│   └── search_results.html # Search results
├── static/
│   ├── css/fairyfloss.css # Dark theme styles
│   ├── js/app.js         # Frontend JavaScript
│   └── fonts/            # DaddyTimeMono font
└── posa_wiki.db          # SQLite database
```

## 🌈 Design Philosophy

**Multi-theme system** with three distinct aesthetics:
- **Fairyfloss**: Dark hacker girl with purples, pinks, and mint
- **Professional**: Clean blue corporate theme (sweater vest and slacks mode)
- **Academia**: Warm paper, parchment, and leather tones

All themes feature rounded edges, semantic color variables, and DaddyTimeMono programming font for a functional yet beautiful interface. Theme preference persists across sessions via localStorage.

## 📋 Status & Roadmap

### ✅ Phase 1: COMPLETE
- ✅ Database schema and population
- ✅ Flask web interface  
- ✅ Core browsing functionality
- ✅ Relationship tracking (people, dogs, trips)
- ✅ Search and filtering

### ✅ Phase 2A: COMPLETE
- ✅ Configuration management (centralized config, .env support)
- ✅ Error handling & logging (custom 404/500 pages, file logging)
- ✅ Full-text search (FTS5) for videos
- ✅ Pagination for all list and detail views
- ✅ Authentication foundations (User model, Flask-Login, CLI for admin creation)
- ✅ Form security (CSRF protection with Flask-WTF)

### 🚧 Phase 2B: Next Priority
- Modal CRUD operations for editing
- Theme/category browsing
- Advanced search filters

### 📋 Phase 3: Planned
- Tag validation interface
- Posaism/reference tracking pages

## 🔧 Quick Start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy and fill in local config (see .env.example for all options)
cp .env.example .env

# Apply migrations not yet reflected in your database, e.g.:
python run_migration.py migrations/009_add_trips_series_type.sql

python app.py
```

Visit http://localhost:5001 to explore the adventure catalog!

See `docs/keeping-current.md` for how project docs are kept in sync as the app evolves.
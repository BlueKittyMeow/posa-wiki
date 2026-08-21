# 🌈 Posa Wiki - Flask Frontend

Dark hacker girl aesthetic with fairyfloss theme and rounded edges for browsing Matthew Posa's adventure videos.

## 🎨 Features

- **Three Theme System**:
  - Fairyfloss (purple/pink/mint dark theme - default)
  - Professional (blue corporate aesthetic)
  - Academia (warm paper/parchment tones)
  - Theme switcher in sidebar with localStorage persistence
- **DaddyTimeMono Font**: Custom programming font for that authentic feel
- **Date-First Navigation**: Jump to any date to find videos published that day
- **People & Dogs Tracking**: Browse adventures by cast members
- **Smart Search**: Full-text search across video titles and descriptions
- **Fully Responsive**: 5 breakpoints (desktop → ultra-small mobile)
- **Mobile Menu**: Slide-out sidebar with backdrop overlay
- **Modal Editing**: Quick CRUD operations without losing your place (Phase 2)

## 🚀 Quick Start

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

The app will start on `http://localhost:5001`

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

## 🎯 Key Pages

- **Landing Page** (`/`) - Date navigation, search, recent videos
- **All Videos** (`/videos`) - Sortable video list with thumbnails
- **People Directory** (`/people`) - Adventure crew members
- **Date View** (`/date/YYYY-MM-DD`) - Videos from specific date
- **Search** (`/search?q=term`) - Full-text search results
- **Video Detail** (`/video/VIDEO_ID`) - Complete video metadata

## 🌈 Design Philosophy

**Multi-Theme System with Three Aesthetics**:
- **Fairyfloss**: Dark hacker girl (purple backgrounds, pastel accents)
- **Professional**: Corporate blue theme (sweater vest and slacks mode)
- **Academia**: Warm paper, parchment, leather tones (library aesthetic)

Design elements across all themes:
- Rounded edges and subtle shadows
- DaddyTimeMono programming font
- Semantic CSS custom properties for easy theming
- Functional but beautiful UI
- FOUC-free theme switching with localStorage persistence

## 🔧 Database Integration

The Flask app connects to the existing SQLite database with:
- **358 videos** with full YouTube metadata
- **9 people** with video relationships
- **3 dogs** (Monty, Rueger) with appearance tracking  
- **13 trips/series** with episodic organization
- **Tag authority system** for categorization

## 🎯 Current Features

- ✅ **Home page** with recent videos and date navigation
- ✅ **All Videos** sortable list with thumbnails
- ✅ **People directory** with video counts and individual profiles
- ✅ **Dogs directory** with adventure tracking
- ✅ **Series browsing** for episodic content
- ✅ **Trip browsing** for multi-day adventures  
- ✅ **Full-text search** across titles and descriptions
- ✅ **Video detail pages** with relationships and metadata
- ✅ **Date-based browsing** to find videos by upload date
- ✅ **Configuration Management**: Centralized config, `.env` support
- ✅ **Error Handling & Logging**: Custom 404/500 pages, file logging
- ✅ **Pagination**: All list and detail views paginated
- ✅ **Authentication**: User model, Flask-Login, CLI for admin creation
- ✅ **Form Security**: CSRF protection

## 📋 Phase 2B TODO

- [ ] Modal CRUD operations for editing content
- [ ] Theme/category browsing pages  
- [ ] Advanced search with people/dog/date filters
- [ ] Tag validation interface
- [ ] Posaism/reference tracking pages
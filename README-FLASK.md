# 🌈 Posa Wiki - Flask Frontend

Dark hacker girl aesthetic with fairyfloss theme and rounded edges for browsing Matthew Posa's adventure videos.

## 🎨 Features

- **Fairyfloss Dark Theme**: Purple, pink, and mint color palette
- **DaddyTimeMono Font**: Custom programming font for that authentic feel
- **Date-First Navigation**: Jump to any date to find videos published that day
- **People & Dogs Tracking**: Browse adventures by cast members
- **Smart Search**: Full-text search across video titles and descriptions
- **Responsive Design**: Works on desktop and mobile
- **Modal Editing**: Quick CRUD operations without losing your place

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

**Dark Hacker Girl Aesthetic**:
- Fairyfloss dark color scheme (purple backgrounds, pastel accents)
- Rounded edges and subtle shadows
- DaddyTimeMono programming font
- Functional but beautiful UI
- TV-friendly dark mode

## 🔧 Database Integration

The Flask app connects to the existing SQLite database with:
- **358 videos** with full YouTube metadata
- **People/Dogs junction tables** populated via description mining
- **Tag authority system** for categorization
- **Rich relationship data** for collaborative videos

## 📝 TODO

- [ ] Modal CRUD operations (currently placeholder)
- [ ] Theme/category browsing pages
- [ ] Trip/series grouping functionality
- [ ] User authentication for admin-only editing
- [ ] Advanced search with filters
- [ ] Video embedding or better YouTube integration
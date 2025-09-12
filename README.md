# 🏕️ Posa Wiki

A fully functional Flask web application for browsing Matthew Posa's outdoor adventure videos with dark hacker girl aesthetic and comprehensive metadata.

## 🚀 Live Features

**Running Flask App**: Start with `python app.py` on http://localhost:5001

- **358 Videos** with full YouTube metadata and thumbnails
- **Dark Fairyfloss Theme** with DaddyTimeMono font
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
- **Video Details** (`/video/ID`) - Full metadata and relationships

## 🌈 Design Philosophy

**Dark hacker girl aesthetic** with fairyfloss color palette (purples, pinks, mint), rounded edges, and programming font for a functional but beautiful interface.

## 📋 Status & Roadmap

### ✅ Phase 1: COMPLETE
- ✅ Database schema and population
- ✅ Flask web interface  
- ✅ Core browsing functionality
- ✅ Relationship tracking (people, dogs, trips)
- ✅ Search and filtering

### 🚧 Phase 2: In Progress  
- Modal CRUD operations for editing
- Theme/category browsing
- Advanced search filters

### 📋 Phase 3: Planned
- User authentication for admin editing
- Tag validation interface
- Posaism/reference tracking pages

## 🔧 Quick Start

```bash
python3 -m venv venv
source venv/bin/activate  
pip install -r requirements.txt
python app.py
```

Visit http://localhost:5001 to explore the adventure catalog!
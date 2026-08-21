# Series Structure Redesign - Overlapping Categories

## Problem with Original Design
Series were treated as mutually exclusive, but Matthew Posa's content often combines multiple themes:
- Winter camping **for** a dog birthday
- Spring camping **on** St. Patrick's Day  
- Canoe camping **in** Boundary Waters **with** Unsuccessful Fishing Show episode

## New Flexible Series Structure

### 🏃 **Activity-Based Series** (Primary camping/adventure type)
- **Canoe Camping** - General paddling adventures (not just Boundary Waters)
- **Winter Camping** - Cold weather adventures
- **Spring Camping** - Spring season adventures  
- **Fall Camping** - Autumn adventures
- **Backpacking** - Multi-day hiking with gear
- **Day Hiking** - Single day outdoor adventures

### 📍 **Location-Specific Series** (Can combine with any activity)
- **Boundary Waters** - Specific wilderness area (subset of Canoe Camping)
- **Isle Royale** - National park adventures
- **Michigan Adventures** - State-specific content
- **Backyard Adventures** - Home-based content

### 🎭 **Content-Type Series** (Can combine with anything)
- **Community Content** - Giveaways + Unboxing + Updates (combined series)
- **Unsuccessful Fishing Show** - Episodic fishing content (numbered)
- **Special Occasions** - Birthdays, holidays, anniversaries

### 🎯 **Example Video Classifications**

**"Winter Camping with My Dog for Monty's Birthday"**
- Series: Winter Camping + Special Occasions + (potentially Community Content if fan mail included)

**"Unsuccessful Fishing Show #12 - Boundary Waters Canoe Trip"**  
- Series: Canoe Camping + Boundary Waters + Unsuccessful Fishing Show

**"Spring Camping St. Patrick's Day Special with Giveaway Results"**
- Series: Spring Camping + Special Occasions + Community Content

**"Backyard Unboxing with Da Boys"**
- Series: Backyard Adventures + Community Content

## Database Implementation

### Series Table Structure (unchanged):
```sql
CREATE TABLE series (
    series_id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,
    description TEXT,
    is_episodic BOOLEAN DEFAULT FALSE,
    series_type VARCHAR -- 'activity', 'location', 'content', 'special'
);
```

### Video-Series Relationships (many-to-many):
```sql  
-- Single video can belong to multiple series
INSERT INTO video_series VALUES
('ABC123', 1, NULL, NULL, 'Winter camping for dog birthday'),  -- Winter Camping
('ABC123', 8, NULL, NULL, 'Birthday celebration'),             -- Special Occasions  
('ABC123', 5, NULL, NULL, 'Fan mail opening');                 -- Community Content
```

### Series Categories:
```sql
INSERT INTO series VALUES
-- Activity-based
(1, 'Winter Camping', 'Cold weather camping adventures', FALSE, 'activity'),
(2, 'Spring Camping', 'Spring season camping adventures', FALSE, 'activity'), 
(3, 'Fall Camping', 'Autumn camping adventures', FALSE, 'activity'),
(4, 'Canoe Camping', 'Paddling and canoe-based adventures', FALSE, 'activity'),
(5, 'Backpacking', 'Multi-day hiking adventures', FALSE, 'activity'),

-- Location-based  
(6, 'Boundary Waters', 'Boundary Waters Canoe Area adventures', FALSE, 'location'),
(7, 'Isle Royale', 'Isle Royale National Park adventures', FALSE, 'location'),
(8, 'Michigan Adventures', 'Michigan-based outdoor content', FALSE, 'location'),

-- Content-type
(9, 'Community Content', 'Giveaways, unboxing, and channel updates', FALSE, 'content'),
(10, 'Unsuccessful Fishing Show', 'Episodic fishing adventure series', TRUE, 'content'),
(11, 'Special Occasions', 'Birthdays, holidays, and celebrations', FALSE, 'special');
```

## Benefits of This Structure

1. **Realistic**: Matches how content actually combines
2. **Flexible**: Videos can have multiple classifications  
3. **Searchable**: Filter by activity + location + content type
4. **Extensible**: Easy to add new series as content evolves
5. **User-Friendly**: Intuitive browsing by different dimensions

**Example Queries:**
- All winter camping videos: `WHERE series_id = 1`
- Boundary Waters canoe trips: `WHERE series_id IN (4,6)` 
- Community content in winter: `WHERE series_id IN (1,9)`
---

## Implemented 2026-08-20 — with owner taxonomy amendments

This design is now live. `series` is the **source of truth for thematic
groupings**; `trips` is reserved for genuine multi-part trips (one adventure
split across several uploads). Amendments to the plan above, all
owner-approved:

- **Winter Camping and Canoe Camping are first-class activity series** (they
  were the two the homepage already advertised).
- **Spring Camping / Fall Camping retired.** Season becomes a *facet* of the
  video record later, not a series. `scripts/seed_series.py` removes the rows
  (it refuses if anything references them) and documents the decision.
- **Community Content stays as an umbrella**, with new child series
  **Unboxing**, **Channel Updates** and **Giveaways**. Membership in a child
  always implies membership in the umbrella — the assignment script writes
  both rows (`notes = 'auto:implied-by-child'`).
- **Holidays are memberships in Special Occasions**, not per-holiday series.
- **New series added:** Day Hiking (activity), Backyard Adventures (location),
  Hike and Cook (content, episodic *by upload date* — the show was never
  numbered), A Winter Camping Christmas Story (content, episodic, numbered
  1–6, the 2017 original being the unnumbered #1).
- **The Unsuccessful Fishing Show migrated out of `trips`.** Its 14 episode
  assignments moved from `video_versions` into `video_series` with
  `episode_number` preserved (`notes = 'migrated:trip-episode'`), and the trip
  row plus its `video_versions` rows were removed. `scripts/update_catalog.py`
  now assigns new episodes to `video_series` against `series.name`.

### Scripts (both idempotent, safe to rerun on the server)

| Script | Job |
|---|---|
| `scripts/seed_series.py` | Upserts the canonical taxonomy **by name** (never by id — production ids differ), retires the season series, migrates the Fishing Show. |
| `scripts/assign_series.py` | Auto-populates `video_series` from title/tag rules. High confidence inserts; medium confidence goes to `data/series_review_candidates.json` for a human. `notes` records which rule fired. |

### App

`/series` reads the `series` table, grouped by `series_type` (Adventure Types
/ Places / Shows & Community / Special), showing member counts and hiding
empty series. `/series/<id>` lists the members — episodic series in episode
order (unnumbered ones by upload date), everything else newest first. Video
detail pages show their series memberships as links alongside the (still
separate) multi-part trip block. Featured-series links look their ids up by
name at render time via the `series_ids` context processor, so nothing
hardcodes an id.

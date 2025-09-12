# YouTube API Scraping Lessons Learned

## Critical Discovery: Search API vs Uploads Playlist

### The Problem
Initial scraping using **YouTube Search API** only returned **339 out of 358 videos** (94.7% coverage), missing 19 important videos.

### Root Cause Analysis
- **Search API** (`youtube/v3/search`): Filtered results, missing some content
- **Uploads Playlist** (`youtube/v3/playlistItems`): Complete channel content

### Missing Video Types Found
The 19 missing videos included valuable content:
- **Giveaway results** ("25k Giveaway Results!")
- **Channel updates** ("Dog Update - What's Happened")
- **Unboxing videos** ("Unboxing A Mountain of Treasures")
- **Special content** ("Monty Puppy Clips!")
- **Birthday specials** ("Hike and Cook - Monty's Birthday!")

### Solution: Uploads Playlist Method

**Correct Approach:**
1. Get channel ID from handle: `@MatthewPosa` → `UCF8HpP-lEx8W9OlMSOW6kGA`
2. Convert to uploads playlist: `UC...` → `UU...` = `UUF8HpP-lEx8W9OlMSOW6kGA`
3. Fetch ALL videos via `playlistItems` API endpoint
4. Process video details in batches

**Code Pattern:**
```python
# Get uploads playlist ID
uploads_playlist_id = channel_id.replace('UC', 'UU')

# Fetch all videos from uploads playlist
url = "https://www.googleapis.com/youtube/v3/playlistItems"
params = {
    'part': 'snippet,contentDetails',
    'playlistId': uploads_playlist_id,
    'maxResults': 50,
    'key': api_key
}
```

### Results
- **Search API**: 339 videos (incomplete)
- **Uploads Playlist**: 358 videos (complete!)
- **Missing videos**: 19 important pieces of content recovered

## Key Takeaway
**Always use the Uploads Playlist method for complete channel scraping.** The Search API may filter or exclude certain video types, leading to incomplete datasets.

## Implementation Files
- `complete_scraper.py` - Full implementation using uploads playlist
- `investigate_missing_videos.py` - Analysis tool for finding gaps
- `import_missing_videos.py` - Tool for importing discovered missing content

## Video Coverage Verification
- Channel reported: **358 videos**
- Database final count: **358 videos** ✅
- Coverage: **100%** complete

This lesson ensures future scraping operations capture ALL channel content without gaps.
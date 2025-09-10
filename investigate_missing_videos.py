#!/usr/bin/env python3
"""
Investigate missing videos from Matthew Posa's channel.
Check for different video types: regular videos, Shorts, live streams, premieres.
"""

import requests
import json
from datetime import datetime

def load_api_key():
    """Load API key from api.md file"""
    try:
        with open('api.md', 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        print("Error: api.md file not found. Please create it with your API key.")
        return None

def get_all_channel_content(api_key, channel_handle="MatthewPosa"):
    """Get ALL content from channel including different video types"""
    
    # First get channel ID
    print(f"🔍 Getting channel info for @{channel_handle}...")
    url = f"https://www.googleapis.com/youtube/v3/channels"
    params = {
        'part': 'id,snippet,statistics',
        'forHandle': channel_handle,
        'key': api_key
    }
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"❌ API Error: {response.text}")
        return
    
    data = response.json()
    if not data['items']:
        print("❌ Channel not found")
        return
    
    channel = data['items'][0]
    channel_id = channel['id']
    video_count = int(channel['statistics']['videoCount'])
    
    print(f"✅ Channel: {channel['snippet']['title']}")
    print(f"   Channel ID: {channel_id}")
    print(f"   Reported video count: {video_count}")
    print()
    
    # Get all videos from uploads playlist
    print("📹 Fetching ALL videos from uploads playlist...")
    uploads_playlist_id = channel_id.replace('UC', 'UU')  # Channel ID -> Uploads playlist ID
    
    all_videos = []
    next_page_token = None
    page_count = 0
    
    while True:
        page_count += 1
        print(f"  Fetching page {page_count}...")
        
        url = "https://www.googleapis.com/youtube/v3/playlistItems"
        params = {
            'part': 'snippet,contentDetails',
            'playlistId': uploads_playlist_id,
            'maxResults': 50,
            'key': api_key
        }
        
        if next_page_token:
            params['pageToken'] = next_page_token
            
        response = requests.get(url, params=params)
        if response.status_code != 200:
            print(f"❌ API Error: {response.text}")
            break
            
        data = response.json()
        
        for item in data.get('items', []):
            video_info = {
                'video_id': item['contentDetails']['videoId'],
                'title': item['snippet']['title'],
                'published': item['snippet']['publishedAt'],
                'position': item['snippet']['position']
            }
            all_videos.append(video_info)
        
        print(f"    Found {len(data.get('items', []))} videos on this page")
        
        next_page_token = data.get('nextPageToken')
        if not next_page_token:
            break
    
    print(f"✅ Total videos found via uploads playlist: {len(all_videos)}")
    
    # Now try search API for any missed content
    print("\n🔍 Searching for any additional content via search API...")
    
    search_videos = []
    next_page_token = None
    
    while True:
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            'part': 'snippet',
            'channelId': channel_id,
            'type': 'video',
            'order': 'date',
            'maxResults': 50,
            'key': api_key
        }
        
        if next_page_token:
            params['pageToken'] = next_page_token
            
        response = requests.get(url, params=params)
        if response.status_code != 200:
            print(f"❌ Search API Error: {response.text}")
            break
            
        data = response.json()
        
        for item in data.get('items', []):
            video_info = {
                'video_id': item['id']['videoId'],
                'title': item['snippet']['title'],
                'published': item['snippet']['publishedAt'],
                'source': 'search'
            }
            search_videos.append(video_info)
        
        next_page_token = data.get('nextPageToken')
        if not next_page_token:
            break
    
    print(f"✅ Total videos found via search: {len(search_videos)}")
    
    # Compare the two methods
    uploads_ids = {v['video_id'] for v in all_videos}
    search_ids = {v['video_id'] for v in search_videos}
    
    print(f"\n📊 Comparison:")
    print(f"   Channel reported: {video_count} videos")
    print(f"   Uploads playlist: {len(uploads_ids)} videos")
    print(f"   Search API: {len(search_ids)} videos")
    print(f"   Videos in both: {len(uploads_ids & search_ids)}")
    print(f"   Only in uploads: {len(uploads_ids - search_ids)}")
    print(f"   Only in search: {len(search_ids - uploads_ids)}")
    
    # Load our current database videos
    import sqlite3
    conn = sqlite3.connect('posa_wiki.db')
    cursor = conn.cursor()
    cursor.execute('SELECT video_id FROM videos')
    db_ids = {row[0] for row in cursor.fetchall()}
    conn.close()
    
    print(f"   In our database: {len(db_ids)} videos")
    
    # Find what we're missing
    all_found_ids = uploads_ids | search_ids
    missing_from_db = all_found_ids - db_ids
    
    print(f"\n🎯 Analysis:")
    print(f"   Total unique videos found: {len(all_found_ids)}")
    print(f"   Missing from our database: {len(missing_from_db)}")
    
    if missing_from_db:
        print(f"\n📝 Missing video IDs:")
        for video_id in list(missing_from_db)[:10]:  # Show first 10
            # Find the video info
            for v in all_videos + search_videos:
                if v['video_id'] == video_id:
                    print(f"   {video_id}: {v['title'][:60]}...")
                    break
        
        if len(missing_from_db) > 10:
            print(f"   ... and {len(missing_from_db) - 10} more")
    
    return all_found_ids, missing_from_db

def main():
    api_key = load_api_key()
    if not api_key:
        return
    
    print("🕵️ INVESTIGATING MISSING VIDEOS")
    print("=" * 50)
    
    all_ids, missing_ids = get_all_channel_content(api_key)
    
    if missing_ids:
        print(f"\n🚀 Found {len(missing_ids)} videos we don't have!")
        print("Next step: Update scraper to collect these videos.")
    else:
        print("\n✅ No missing videos found. Our database is complete!")

if __name__ == "__main__":
    main()
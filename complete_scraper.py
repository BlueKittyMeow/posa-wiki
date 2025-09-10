#!/usr/bin/env python3
"""
Complete channel scraper using uploads playlist method.
Gets ALL videos (358) including the 19 missing ones.
"""

import requests
import json
import time
from datetime import datetime

def load_api_key():
    """Load API key from api.md file"""
    try:
        with open('api.md', 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        print("Error: api.md file not found. Please create it with your API key.")
        return None

def get_all_video_ids(api_key, channel_handle="MatthewPosa"):
    """Get ALL video IDs using uploads playlist method"""
    
    # Get channel info
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
        return None, 0
    
    data = response.json()
    if not data['items']:
        print("❌ Channel not found")
        return None, 0
    
    channel = data['items'][0]
    channel_id = channel['id']
    video_count = int(channel['statistics']['videoCount'])
    
    print(f"✅ Channel: {channel['snippet']['title']}")
    print(f"   Video count: {video_count}")
    print(f"   Channel ID: {channel_id}")
    print()
    
    # Get uploads playlist ID (UC -> UU)
    uploads_playlist_id = channel_id.replace('UC', 'UU')
    print(f"📹 Fetching ALL videos from uploads playlist: {uploads_playlist_id}")
    
    video_ids = []
    next_page_token = None
    page_count = 0
    
    while True:
        page_count += 1
        print(f"  Page {page_count}: Fetching up to 50 videos...")
        
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
        page_videos = []
        
        for item in data.get('items', []):
            video_info = {
                'video_id': item['contentDetails']['videoId'],
                'position': item['snippet']['position']
            }
            page_videos.append(video_info)
            video_ids.append(video_info)
        
        print(f"    Collected {len(page_videos)} videos so far...")
        
        next_page_token = data.get('nextPageToken')
        if not next_page_token:
            break
    
    print(f"✅ Found {len(video_ids)} total videos")
    return video_ids, video_count

def get_video_details_batch(api_key, video_ids_batch):
    """Get detailed metadata for a batch of videos"""
    video_ids_only = [v['video_id'] for v in video_ids_batch]
    video_ids_str = ','.join(video_ids_only)
    
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        'part': 'id,snippet,contentDetails,statistics',
        'id': video_ids_str,
        'key': api_key
    }
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"❌ Error fetching video details: {response.text}")
        return []
    
    return response.json().get('items', [])

def scrape_complete_channel():
    """Scrape complete channel using uploads playlist method"""
    api_key = load_api_key()
    if not api_key:
        return
    
    start_time = datetime.now()
    print(f"🚀 Starting COMPLETE channel scrape at {start_time}")
    print("=" * 60)
    
    # Get all video IDs
    video_ids, expected_count = get_all_video_ids(api_key)
    if not video_ids:
        return
    
    print(f"\\nProcessing {len(video_ids)} videos in batches of 50...")
    
    # Process videos in batches
    all_videos = []
    batch_size = 50
    
    for i in range(0, len(video_ids), batch_size):
        batch_num = i // batch_size + 1
        total_batches = (len(video_ids) + batch_size - 1) // batch_size
        
        batch = video_ids[i:i + batch_size]
        print(f"  Batch {batch_num}/{total_batches}: Processing {len(batch)} videos...")
        
        video_details = get_video_details_batch(api_key, batch)
        all_videos.extend(video_details)
        
        print(f"    ✅ Got detailed data for {len(video_details)} videos")
        
        # Small delay to be nice to API
        time.sleep(0.1)
    
    print(f"✅ Processed {len(all_videos)} videos total")
    
    # Analyze tags
    print(f"\\n📊 Dataset Analysis:")
    print(f"   Total videos: {len(all_videos)}")
    
    videos_with_duration = sum(1 for v in all_videos if v.get('contentDetails', {}).get('duration'))
    videos_with_tags = sum(1 for v in all_videos if v.get('snippet', {}).get('tags'))
    
    print(f"   Videos with duration: {videos_with_duration}")
    print(f"   Videos with tags: {videos_with_tags}")
    
    # Count unique tags
    all_tags = []
    for video in all_videos:
        tags = video.get('snippet', {}).get('tags', [])
        all_tags.extend([tag.lower() for tag in tags])
    
    unique_tags = len(set(all_tags))
    print(f"   Total unique tags: {unique_tags}")
    
    # Show most common tags
    from collections import Counter
    tag_counts = Counter(all_tags)
    print(f"\\n   Top 20 most common tags:")
    for tag, count in tag_counts.most_common(20):
        print(f"     {tag}: {count}")
    
    # Save results
    filename = f"complete_channel_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    result_data = {
        'scrape_timestamp': datetime.now().isoformat(),
        'channel_handle': 'MatthewPosa',
        'expected_video_count': expected_count,
        'actual_video_count': len(all_videos),
        'scrape_method': 'uploads_playlist',
        'videos': all_videos
    }
    
    with open(filename, 'w') as f:
        json.dump(result_data, f, indent=2)
    
    duration = datetime.now() - start_time
    
    print(f"\\n🎉 COMPLETE Scrape finished!")
    print(f"   Duration: {duration}")
    print(f"   Saved to: {filename}")
    print(f"   Videos processed: {len(all_videos)}")
    print(f"   Expected vs Actual: {expected_count} vs {len(all_videos)}")
    
    if len(all_videos) == expected_count:
        print("   ✅ PERFECT MATCH! Got all videos!")
    else:
        print(f"   ⚠️  Still missing {expected_count - len(all_videos)} videos")

if __name__ == "__main__":
    scrape_complete_channel()
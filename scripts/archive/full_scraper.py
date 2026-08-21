#!/usr/bin/env python3
"""
Full channel scraper for Matthew Posa's YouTube channel.
This will fetch ALL 339 videos with complete metadata and save to JSON for analysis.
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

def get_channel_info(api_key):
    """Get basic channel information"""
    print("Getting channel info...")
    
    url = f"https://www.googleapis.com/youtube/v3/channels"
    params = {
        'part': 'id,snippet,statistics',
        'forHandle': 'MatthewPosa',
        'key': api_key
    }
    
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data['items']:
            channel = data['items'][0]
            print(f"✅ Channel: {channel['snippet']['title']}")
            print(f"   Video count: {channel['statistics']['videoCount']}")
            print(f"   Channel ID: {channel['id']}")
            return channel['id'], int(channel['statistics']['videoCount'])
    
    print(f"❌ API Error: {response.text}")
    return None, 0

def get_all_video_ids(api_key, channel_id, total_videos):
    """Get ALL video IDs from the channel"""
    print(f"\nFetching all {total_videos} video IDs...")
    
    url = f"https://www.googleapis.com/youtube/v3/search"
    video_ids = []
    next_page_token = None
    page_count = 0
    
    while True:
        page_count += 1
        params = {
            'part': 'id,snippet',  # Get snippet for basic info
            'channelId': channel_id,
            'maxResults': 50,  # Max allowed
            'order': 'date',  # Chronological order
            'type': 'video',
            'key': api_key
        }
        
        if next_page_token:
            params['pageToken'] = next_page_token
        
        print(f"  Page {page_count}: Fetching up to 50 videos...")
        response = requests.get(url, params=params)
        
        if response.status_code != 200:
            print(f"❌ API Error: {response.text}")
            break
            
        data = response.json()
        
        # Store basic info for each video
        for item in data['items']:
            video_info = {
                'video_id': item['id']['videoId'],
                'title': item['snippet']['title'],
                'upload_date': item['snippet']['publishedAt'],
                'description_preview': item['snippet']['description'][:200]  # First 200 chars
            }
            video_ids.append(video_info)
        
        print(f"    Collected {len(video_ids)} videos so far...")
        
        # Rate limiting - be nice to the API
        time.sleep(0.1)
        
        # Check if there are more pages
        next_page_token = data.get('nextPageToken')
        if not next_page_token:
            break
    
    print(f"✅ Found {len(video_ids)} total videos")
    return video_ids

def get_video_details_batch(api_key, video_ids_batch):
    """Get detailed metadata for a batch of videos"""
    video_ids_only = [v['video_id'] for v in video_ids_batch]
    
    url = f"https://www.googleapis.com/youtube/v3/videos"
    params = {
        'part': 'id,snippet,contentDetails,statistics',
        'id': ','.join(video_ids_only),
        'key': api_key
    }
    
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"❌ Batch API Error: {response.text}")
        return None

def process_all_videos(api_key, video_list):
    """Process all videos in batches to get complete metadata"""
    print(f"\nProcessing {len(video_list)} videos in batches of 50...")
    
    all_detailed_videos = []
    batch_size = 50
    
    for i in range(0, len(video_list), batch_size):
        batch = video_list[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(video_list) + batch_size - 1) // batch_size
        
        print(f"  Batch {batch_num}/{total_batches}: Processing {len(batch)} videos...")
        
        detailed_data = get_video_details_batch(api_key, batch)
        if detailed_data and 'items' in detailed_data:
            all_detailed_videos.extend(detailed_data['items'])
            print(f"    ✅ Got detailed data for {len(detailed_data['items'])} videos")
        else:
            print(f"    ❌ Failed to get detailed data for this batch")
        
        # Rate limiting
        time.sleep(0.5)
    
    print(f"✅ Processed {len(all_detailed_videos)} videos total")
    return all_detailed_videos

def analyze_data_patterns(videos):
    """Quick analysis of the full dataset for schema planning"""
    print(f"\n📊 Dataset Analysis:")
    print(f"   Total videos: {len(videos)}")
    
    # Duration analysis
    durations = []
    for video in videos:
        duration = video.get('contentDetails', {}).get('duration', '')
        if duration:
            durations.append(duration)
    
    print(f"   Videos with duration: {len(durations)}")
    
    # Tag analysis
    all_tags = []
    videos_with_tags = 0
    for video in videos:
        tags = video.get('snippet', {}).get('tags', [])
        if tags:
            videos_with_tags += 1
            all_tags.extend(tags)
    
    print(f"   Videos with tags: {videos_with_tags}")
    print(f"   Total unique tags: {len(set(all_tags))}")
    
    # Most common tags (for authority building)
    from collections import Counter
    if all_tags:
        common_tags = Counter(all_tags).most_common(20)
        print(f"\n   Top 20 most common tags:")
        for tag, count in common_tags:
            print(f"     {tag}: {count}")

def main():
    start_time = datetime.now()
    print(f"🚀 Starting full channel scrape at {start_time}")
    
    # Load API key
    api_key = load_api_key()
    if not api_key:
        return
    
    # Get channel info
    channel_id, video_count = get_channel_info(api_key)
    if not channel_id:
        return
    
    # Get all video IDs and basic info
    video_list = get_all_video_ids(api_key, channel_id, video_count)
    if not video_list:
        return
    
    # Get detailed metadata for all videos
    all_videos = process_all_videos(api_key, video_list)
    if not all_videos:
        return
    
    # Save complete dataset
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f'full_channel_scrape_{timestamp}.json'
    
    output_data = {
        'scrape_info': {
            'timestamp': timestamp,
            'total_videos': len(all_videos),
            'channel_id': channel_id,
            'scrape_duration_minutes': (datetime.now() - start_time).seconds / 60
        },
        'videos': all_videos
    }
    
    with open(filename, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    # Quick analysis
    analyze_data_patterns(all_videos)
    
    end_time = datetime.now()
    duration = end_time - start_time
    
    print(f"\n🎉 Scrape complete!")
    print(f"   Duration: {duration}")
    print(f"   Saved to: {filename}")
    print(f"   Videos processed: {len(all_videos)}")

if __name__ == "__main__":
    main()
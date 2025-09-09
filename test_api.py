#!/usr/bin/env python3
"""
Test script to verify YouTube Data API access and explore Matthew Posa's channel data.
This will fetch basic channel info and the 10 oldest videos.
"""

import requests
import json

def load_api_key():
    """Load API key from api.md file"""
    try:
        with open('api.md', 'r') as f:
            # Assuming the API key is just plain text in the file
            return f.read().strip()
    except FileNotFoundError:
        print("Error: api.md file not found. Please create it with your API key.")
        return None

def test_channel_access(api_key):
    """Test basic channel access and get channel ID"""
    print("Testing channel access...")
    
    # Get channel info using handle
    url = f"https://www.googleapis.com/youtube/v3/channels"
    params = {
        'part': 'id,snippet,statistics',
        'forHandle': 'MatthewPosa',
        'key': api_key
    }
    
    response = requests.get(url, params=params)
    print(f"Channel API Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data['items']:
            channel = data['items'][0]
            channel_id = channel['id']
            channel_name = channel['snippet']['title']
            video_count = channel['statistics']['videoCount']
            
            print(f"✅ Found channel: {channel_name}")
            print(f"   Channel ID: {channel_id}")
            print(f"   Video count: {video_count}")
            return channel_id
        else:
            print("❌ No channel found with that handle")
            return None
    else:
        print(f"❌ API Error: {response.text}")
        return None

def get_all_video_ids(api_key, channel_id):
    """Get ALL video IDs from the channel, then sort to find oldest"""
    print(f"\nFetching all video IDs to find oldest...")
    
    url = f"https://www.googleapis.com/youtube/v3/search"
    video_ids = []
    next_page_token = None
    
    while True:
        params = {
            'part': 'id',
            'channelId': channel_id,
            'maxResults': 50,  # Max allowed
            'order': 'date',
            'type': 'video',
            'key': api_key
        }
        
        if next_page_token:
            params['pageToken'] = next_page_token
        
        response = requests.get(url, params=params)
        if response.status_code != 200:
            print(f"❌ API Error: {response.text}")
            break
            
        data = response.json()
        
        # Extract video IDs
        for item in data['items']:
            video_ids.append(item['id']['videoId'])
        
        print(f"  Collected {len(video_ids)} video IDs so far...")
        
        # Check if there are more pages
        next_page_token = data.get('nextPageToken')
        if not next_page_token:
            break
    
    print(f"✅ Found {len(video_ids)} total videos")
    
    # Return the LAST 10 (oldest) video IDs
    oldest_10_ids = video_ids[-10:] if len(video_ids) >= 10 else video_ids
    return oldest_10_ids

def get_video_details(api_key, video_ids):
    """Get detailed video metadata including full descriptions, duration, view counts"""
    print(f"\nFetching detailed metadata for {len(video_ids)} videos...")
    
    url = f"https://www.googleapis.com/youtube/v3/videos"
    params = {
        'part': 'id,snippet,contentDetails,statistics',
        'id': ','.join(video_ids),
        'key': api_key
    }
    
    response = requests.get(url, params=params)
    print(f"Video Details API Status: {response.status_code}")
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"❌ API Error: {response.text}")
        return None

def main():
    # Load API key
    api_key = load_api_key()
    if not api_key:
        return
    
    # Test channel access
    channel_id = test_channel_access(api_key)
    if not channel_id:
        return
    
    # Get oldest video IDs
    oldest_video_ids = get_all_video_ids(api_key, channel_id)
    if not oldest_video_ids:
        return
    
    print(f"\nOldest 10 video IDs: {oldest_video_ids}")
    
    # Get detailed video metadata
    videos_data = get_video_details(api_key, oldest_video_ids)
    if videos_data:
        # Save to exploratory file
        filename = 'exploratory_test_oldest_10_fixed.json'
        with open(filename, 'w') as f:
            json.dump(videos_data, f, indent=2)
        
        print(f"\n✅ Saved {len(videos_data.get('items', []))} videos to {filename}")
        
        # Show a preview
        print("\nPreview of video titles (should be oldest now):")
        for i, item in enumerate(videos_data.get('items', [])[:3]):
            title = item['snippet']['title']
            date = item['snippet']['publishedAt'][:10]  # Just the date part
            duration = item['contentDetails']['duration']
            view_count = item['statistics'].get('viewCount', 'N/A')
            desc_preview = item['snippet']['description'][:100] + "..." if len(item['snippet']['description']) > 100 else item['snippet']['description']
            
            print(f"  {i+1}. {title} ({date})")
            print(f"     Duration: {duration}, Views: {view_count}")
            print(f"     Desc: {desc_preview}")
            print()
        
        if len(videos_data.get('items', [])) > 3:
            print(f"  ... and {len(videos_data.get('items', [])) - 3} more")
    
    print(f"\n🎉 Test complete! Check {filename} for full data with complete descriptions.")

if __name__ == "__main__":
    main()
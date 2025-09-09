#!/usr/bin/env python3
"""
Test script to investigate YouTube chapters and auto-generated subtitles.
"""

import requests
import json

def load_api_key():
    with open('api.md', 'r') as f:
        return f.read().strip()

def test_chapters_api(api_key, video_id):
    """Test if YouTube Data API provides chapter information"""
    print(f"🔍 Testing chapters for video: {video_id}")
    
    # Try getting chapters from videos endpoint with different parts
    parts_to_try = [
        'snippet,contentDetails,statistics',
        'snippet,contentDetails,statistics,chapters',
        'snippet,contentDetails,statistics,localizations',
        'snippet,contentDetails,statistics,player'
    ]
    
    for part in parts_to_try:
        print(f"  Trying part: {part}")
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {
            'part': part,
            'id': video_id,
            'key': api_key
        }
        
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            if data['items']:
                video = data['items'][0]
                print(f"    ✅ Success - Keys available: {list(video.keys())}")
                
                # Look for chapter-related data
                for key, value in video.items():
                    if 'chapter' in str(key).lower() or 'chapter' in str(value).lower():
                        print(f"    🎯 Found chapter data: {key} = {value}")
                
                # Check if description contains manual chapters
                description = video.get('snippet', {}).get('description', '')
                chapter_patterns = []
                import re
                # Look for timestamp patterns like "0:00", "1:23", "12:34"
                timestamps = re.findall(r'(\d{1,2}:\d{2}(?::\d{2})?)', description)
                if timestamps:
                    print(f"    📝 Found {len(timestamps)} timestamps in description: {timestamps[:5]}...")
                    chapter_patterns = timestamps
                
                return video, chapter_patterns
            else:
                print(f"    ❌ No video data returned")
        else:
            print(f"    ❌ API Error {response.status_code}: {response.text[:100]}...")
    
    return None, []

def test_captions_api(api_key, video_id):
    """Test if we can get captions/subtitles"""
    print(f"\n🗣️  Testing captions for video: {video_id}")
    
    # First, get available caption tracks
    url = "https://www.googleapis.com/youtube/v3/captions"
    params = {
        'part': 'snippet',
        'videoId': video_id,
        'key': api_key
    }
    
    response = requests.get(url, params=params)
    print(f"  Captions API Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"  Available caption tracks: {len(data.get('items', []))}")
        
        for track in data.get('items', []):
            track_info = track.get('snippet', {})
            language = track_info.get('language', 'unknown')
            track_kind = track_info.get('trackKind', 'unknown')
            name = track_info.get('name', 'unnamed')
            print(f"    • {language} ({track_kind}): {name}")
        
        return data
    else:
        print(f"  ❌ Captions API Error: {response.text[:100]}...")
        return None

def analyze_sample_videos(api_key):
    """Test chapters/captions on a few sample videos"""
    # Get a few video IDs from our dataset
    with open('full_channel_scrape_20250902_142647.json', 'r') as f:
        dataset = json.load(f)
    
    # Test on first 3 videos and some with longer descriptions
    test_videos = []
    for video in dataset['videos'][:5]:
        video_id = video['id']
        title = video['snippet']['title']
        desc_length = len(video['snippet']['description'])
        test_videos.append((video_id, title, desc_length))
    
    print("🧪 TESTING CHAPTERS AND CAPTIONS")
    print("=" * 50)
    
    chapter_results = {}
    caption_results = {}
    
    for video_id, title, desc_length in test_videos:
        print(f"\n📹 Video: {title[:50]}...")
        print(f"   Description length: {desc_length} characters")
        
        # Test chapters
        video_data, chapters = test_chapters_api(api_key, video_id)
        chapter_results[video_id] = {
            'title': title,
            'manual_chapters': chapters,
            'has_chapters': len(chapters) > 0
        }
        
        # Test captions  
        captions = test_captions_api(api_key, video_id)
        caption_results[video_id] = {
            'title': title,
            'has_captions': captions is not None and len(captions.get('items', [])) > 0,
            'caption_tracks': captions.get('items', []) if captions else []
        }
        
        print("  " + "─" * 40)
    
    # Summary
    print(f"\n📊 RESULTS SUMMARY:")
    print(f"   Videos tested: {len(test_videos)}")
    
    videos_with_chapters = sum(1 for r in chapter_results.values() if r['has_chapters'])
    videos_with_captions = sum(1 for r in caption_results.values() if r['has_captions'])
    
    print(f"   Videos with manual chapter timestamps: {videos_with_chapters}/{len(test_videos)}")
    print(f"   Videos with available captions: {videos_with_captions}/{len(test_videos)}")
    
    if videos_with_chapters > 0:
        print(f"\n📝 CHAPTER EXAMPLES:")
        for video_id, data in chapter_results.items():
            if data['has_chapters']:
                print(f"     {data['title'][:40]}...")
                print(f"       Timestamps: {data['manual_chapters'][:3]}")
    
    return chapter_results, caption_results

def main():
    api_key = load_api_key()
    if not api_key:
        return
        
    chapter_results, caption_results = analyze_sample_videos(api_key)
    
    # Save results for analysis
    results = {
        'timestamp': '2025-01-02',
        'chapter_results': chapter_results,
        'caption_results': caption_results
    }
    
    with open('chapters_captions_test.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Results saved to chapters_captions_test.json")

if __name__ == "__main__":
    main()
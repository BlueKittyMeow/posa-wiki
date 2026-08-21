#!/usr/bin/env python3
"""
Comprehensive trip and series detection system.
Analyzes all videos to find multi-part content and create trip groupings.
"""

import sqlite3
import re
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import json

def analyze_multipart_videos():
    """Find all potential multi-part video series"""
    conn = sqlite3.connect('posa_wiki.db')
    videos = conn.execute('''
    SELECT video_id, title, upload_date, description 
    FROM videos 
    ORDER BY upload_date DESC
    ''').fetchall()
    
    print(f"🔍 ANALYZING {len(videos)} VIDEOS FOR TRIP PATTERNS")
    print("=" * 60)
    
    # Pattern detection
    explicit_series = {}  # Series with clear part indicators
    potential_series = defaultdict(list)  # Similar titles that might be related
    standalone_candidates = []  # Videos that might be standalone trips
    
    # Explicit multi-part patterns
    part_patterns = [
        (r'(.+?)\s*\(?\s*part\s+(\d+)\s*of\s+(\d+)\s*\)?', 'part_of'),
        (r'(.+?)\s*\(?\s*episode\s+(\d+)', 'episode'),
        (r'(.+?)\s*-\s*day\s+(\d+)', 'day'),
        (r'(.+?)\s*-\s*night\s+(\d+)', 'night'),
        (r'(.+?)\s*\[(\d+)\s*of\s*(\d+)\]', 'bracket_part'),
    ]
    
    # Trip indicators in titles
    trip_keywords = [
        'night', 'day', 'wilderness', 'adventure', 'canoe', 'camping',
        'expedition', 'journey', 'backpack', 'hike', 'paddle'
    ]
    
    for video in videos:
        video_id, title, upload_date, description = video
        title_lower = title.lower()
        
        # Check for explicit part indicators
        found_explicit = False
        for pattern, pattern_type in part_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                if pattern_type == 'part_of':
                    base_title = match.group(1).strip()
                    part_num = int(match.group(2))
                    total_parts = int(match.group(3))
                    series_key = f"{base_title}___PARTS_{total_parts}"
                else:
                    base_title = match.group(1).strip()
                    part_num = int(match.group(2))
                    series_key = f"{base_title}___TYPE_{pattern_type}"
                
                if series_key not in explicit_series:
                    explicit_series[series_key] = []
                explicit_series[series_key].append({
                    'video_id': video_id,
                    'title': title,
                    'upload_date': upload_date,
                    'part_number': part_num,
                    'base_title': base_title
                })
                found_explicit = True
                break
        
        if not found_explicit:
            # Look for trip indicators
            trip_score = sum(1 for keyword in trip_keywords if keyword in title_lower)
            
            # Extract potential base title (remove common suffixes)
            base_title = title
            # Remove common descriptive suffixes
            suffixes_to_remove = [
                r'\s*-\s*.*',  # Everything after dash
                r'\s*\(.*?\)',  # Parenthetical content
                r'\s*\[.*?\]',  # Bracketed content
                r'\s+with\s+.*',  # "with my dog" etc
                r'\s+in\s+.*',   # Location info
            ]
            
            for suffix_pattern in suffixes_to_remove:
                base_title = re.sub(suffix_pattern, '', base_title, flags=re.IGNORECASE)
            
            base_title = base_title.strip()
            
            if trip_score >= 2 or len(base_title) < len(title) * 0.6:  # Significant content removed
                potential_series[base_title].append({
                    'video_id': video_id,
                    'title': title,
                    'upload_date': upload_date,
                    'trip_score': trip_score,
                    'base_title': base_title
                })
    
    # Analyze results
    print("\n🎬 EXPLICIT MULTI-PART SERIES:")
    confirmed_trips = []
    
    for series_key, videos in explicit_series.items():
        if len(videos) > 1:
            base_title = series_key.split('___')[0]
            videos_sorted = sorted(videos, key=lambda x: x['part_number'])
            
            print(f"\n📺 {base_title}")
            print(f"   Parts: {len(videos_sorted)}")
            
            trip_data = {
                'base_title': base_title,
                'type': 'explicit_series',
                'confidence': 'high',
                'videos': videos_sorted
            }
            confirmed_trips.append(trip_data)
            
            for v in videos_sorted:
                print(f"   • Part {v['part_number']}: {v['title']} ({v['upload_date'][:10]})")
    
    print(f"\n📊 POTENTIAL SERIES (Similar Titles):")
    for base_title, videos in potential_series.items():
        if len(videos) > 1:
            videos_sorted = sorted(videos, key=lambda x: x['upload_date'])
            date_span = (datetime.fromisoformat(videos_sorted[-1]['upload_date'][:10]) - 
                        datetime.fromisoformat(videos_sorted[0]['upload_date'][:10])).days
            
            # Filter for likely series (reasonable date span, similar trip scores)
            if date_span < 365:  # Within a year
                avg_score = sum(v['trip_score'] for v in videos) / len(videos)
                print(f"\n🤔 {base_title} ({len(videos)} videos, {date_span} days apart)")
                
                trip_data = {
                    'base_title': base_title,
                    'type': 'potential_series',
                    'confidence': 'medium' if avg_score >= 2 else 'low',
                    'videos': videos_sorted,
                    'date_span_days': date_span
                }
                confirmed_trips.append(trip_data)
                
                for v in videos_sorted:
                    print(f"   • {v['title']} ({v['upload_date'][:10]}) [score: {v['trip_score']}]")
    
    print(f"\n📈 SUMMARY:")
    print(f"   Explicit series found: {len([t for t in confirmed_trips if t['type'] == 'explicit_series'])}")
    print(f"   Potential series found: {len([t for t in confirmed_trips if t['type'] == 'potential_series'])}")
    print(f"   Total videos in series: {sum(len(t['videos']) for t in confirmed_trips)}")
    
    # Save results for review
    with open('trip_analysis_results.json', 'w') as f:
        json.dump(confirmed_trips, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to trip_analysis_results.json")
    print(f"📋 Review these results and confirm which trips to create in database")
    
    conn.close()
    return confirmed_trips

if __name__ == "__main__":
    analyze_multipart_videos()
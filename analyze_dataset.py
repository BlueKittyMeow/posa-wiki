#!/usr/bin/env python3
"""
Comprehensive analysis of the full Matthew Posa dataset.
Identifies patterns for schema improvements and authority control.
"""

import json
import re
from collections import Counter, defaultdict
from datetime import datetime

def load_dataset():
    """Load the scraped dataset"""
    with open('full_channel_scrape_20250902_142647.json', 'r') as f:
        return json.load(f)

def analyze_tags(videos):
    """Deep analysis of YouTube tags for authority control"""
    print("🏷️  TAG ANALYSIS")
    
    all_tags = []
    tag_video_count = Counter()
    
    for video in videos:
        tags = video.get('snippet', {}).get('tags', [])
        for tag in tags:
            all_tags.append(tag.lower())  # Normalize case
            tag_video_count[tag.lower()] += 1
    
    print(f"   Total tags: {len(all_tags)}")
    print(f"   Unique tags: {len(set(all_tags))}")
    
    # Find potential authority control issues
    location_patterns = []
    activity_patterns = []
    people_patterns = []
    dog_patterns = []
    misspelling_candidates = []
    
    for tag, count in tag_video_count.most_common(200):  # Top 200 tags
        tag_lower = tag.lower()
        
        # Location patterns
        if any(loc in tag_lower for loc in ['water', 'lake', 'river', 'forest', 'park', 'michigan', 'island', 'bwca', 'boundary']):
            location_patterns.append((tag, count))
        
        # Activity patterns  
        if any(act in tag_lower for act in ['camp', 'fish', 'cook', 'winter', 'snow', 'fire', 'bushcraft', 'survival']):
            activity_patterns.append((tag, count))
            
        # People patterns
        if any(person in tag_lower for person in ['teeny', 'lucas', 'matthew', 'posa', 'friend']):
            people_patterns.append((tag, count))
            
        # Dog patterns
        if any(dog in tag_lower for dog in ['dog', 'puppy', 'monty', 'rueger', 'collie']):
            dog_patterns.append((tag, count))
    
    print(f"\n📍 LOCATION TAGS ({len(location_patterns)}):")
    for tag, count in location_patterns[:15]:
        print(f"     {tag}: {count}")
    
    print(f"\n🎯 ACTIVITY TAGS ({len(activity_patterns)}):")  
    for tag, count in activity_patterns[:15]:
        print(f"     {tag}: {count}")
        
    print(f"\n🐕 DOG TAGS ({len(dog_patterns)}):")
    for tag, count in dog_patterns[:15]:
        print(f"     {tag}: {count}")
    
    # Find potential misspellings/variants
    print(f"\n🔤 POTENTIAL VARIANTS/MISSPELLINGS:")
    tag_groups = defaultdict(list)
    for tag, count in tag_video_count.items():
        if count >= 5:  # Only consider tags used 5+ times
            # Group by first few letters
            key = tag[:4].lower() if len(tag) >= 4 else tag.lower()
            tag_groups[key].append((tag, count))
    
    for key, variants in tag_groups.items():
        if len(variants) > 1:  # Multiple variants of similar tags
            print(f"     {key}*: {variants}")

def analyze_descriptions(videos):
    """Analyze descriptions for gear lists, locations, people mentions"""
    print(f"\n📝 DESCRIPTION ANALYSIS")
    
    gear_mentions = Counter()
    location_mentions = Counter()
    people_mentions = Counter()
    nights_patterns = []
    
    for video in videos:
        desc = video.get('snippet', {}).get('description', '').lower()
        title = video.get('snippet', {}).get('title', '').lower()
        combined = f"{title} {desc}"
        
        # Extract nights patterns
        nights_matches = re.findall(r'(\d+)\s*(night|day)s?', combined)
        for match in nights_matches:
            nights_patterns.append(f"{match[0]} {match[1]}")
        
        # Common gear patterns
        gear_patterns = ['knife', 'axe', 'tent', 'sleeping bag', 'stove', 'fire', 'pack', 'boots', 'jacket']
        for gear in gear_patterns:
            if gear in desc:
                gear_mentions[gear] += 1
        
        # Location patterns
        location_patterns = ['boundary waters', 'bwca', 'michigan', 'lake', 'river', 'forest', 'park', 'island']
        for location in location_patterns:
            if location in combined:
                location_mentions[location] += 1
        
        # People patterns
        people_patterns = ['teeny trout', 'lucas', 'jake', 'friend', 'buddy']
        for person in people_patterns:
            if person in combined:
                people_mentions[person] += 1
    
    print(f"   Nights patterns found: {len(nights_patterns)}")
    nights_counter = Counter(nights_patterns)
    for pattern, count in nights_counter.most_common(10):
        print(f"     {pattern}: {count}")
    
    print(f"\n🎒 GEAR MENTIONS:")
    for gear, count in gear_mentions.most_common(10):
        print(f"     {gear}: {count}")
    
    print(f"\n📍 LOCATION MENTIONS:")
    for location, count in location_mentions.most_common(10):
        print(f"     {location}: {count}")
    
    print(f"\n👥 PEOPLE MENTIONS:")
    for person, count in people_mentions.most_common(10):
        print(f"     {person}: {count}")

def analyze_temporal_patterns(videos):
    """Analyze upload patterns and duration trends"""
    print(f"\n📅 TEMPORAL ANALYSIS")
    
    years = Counter()
    months = Counter()
    durations = []
    
    for video in videos:
        # Upload date analysis
        upload_date = video.get('snippet', {}).get('publishedAt', '')
        if upload_date:
            year = upload_date[:4]
            month = upload_date[5:7]
            years[year] += 1
            months[month] += 1
        
        # Duration analysis
        duration = video.get('contentDetails', {}).get('duration', '')
        if duration:
            # Parse ISO 8601 duration (PT18M49S)
            duration_match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
            if duration_match:
                hours = int(duration_match.group(1) or 0)
                minutes = int(duration_match.group(2) or 0)
                seconds = int(duration_match.group(3) or 0)
                total_seconds = hours * 3600 + minutes * 60 + seconds
                durations.append(total_seconds)
    
    print(f"   Videos by year:")
    for year, count in sorted(years.items()):
        print(f"     {year}: {count}")
    
    print(f"\n   Videos by month:")
    for month, count in sorted(months.items()):
        month_name = datetime.strptime(month, '%m').strftime('%B')
        print(f"     {month_name}: {count}")
    
    if durations:
        avg_duration = sum(durations) / len(durations)
        min_duration = min(durations)
        max_duration = max(durations)
        print(f"\n   Duration stats:")
        print(f"     Average: {avg_duration/60:.1f} minutes")
        print(f"     Shortest: {min_duration/60:.1f} minutes")
        print(f"     Longest: {max_duration/60:.1f} minutes")

def suggest_authority_records(videos):
    """Suggest authority records based on analysis"""
    print(f"\n🎯 SUGGESTED AUTHORITY RECORDS")
    
    # Top tags that need authority control
    all_tags = []
    for video in videos:
        tags = video.get('snippet', {}).get('tags', [])
        all_tags.extend([tag.lower() for tag in tags])
    
    tag_counts = Counter(all_tags)
    
    print(f"\n📍 LOCATION AUTHORITY (top location-related tags):")
    location_tags = [tag for tag, count in tag_counts.most_common() 
                    if any(loc in tag for loc in ['boundary', 'bwca', 'water', 'lake', 'michigan', 'island', 'park'])]
    for tag in location_tags[:10]:
        print(f"     • {tag} ({tag_counts[tag]} videos)")
        # Suggest canonical form
        if 'bwca' in tag:
            print(f"       → Canonical: 'Boundary Waters Canoe Area'")
        elif 'michigan' in tag:
            print(f"       → Canonical: 'Michigan'")
    
    print(f"\n🎯 ACTIVITY AUTHORITY (top activity tags):")
    activity_tags = [tag for tag, count in tag_counts.most_common() 
                    if any(act in tag for act in ['camp', 'bushcraft', 'winter', 'fish', 'cook', 'fire', 'survival'])]
    for tag in activity_tags[:15]:
        print(f"     • {tag} ({tag_counts[tag]} videos)")
    
    print(f"\n🐕 DOG/PEOPLE AUTHORITY:")
    entity_tags = [tag for tag, count in tag_counts.most_common() 
                  if any(ent in tag for ent in ['dog', 'monty', 'rueger', 'teeny', 'collie'])]
    for tag in entity_tags[:10]:
        print(f"     • {tag} ({tag_counts[tag]} videos)")

def main():
    print("📊 MATTHEW POSA DATASET ANALYSIS")
    print("=" * 50)
    
    dataset = load_dataset()
    videos = dataset['videos']
    
    print(f"Dataset: {len(videos)} videos")
    print(f"Scraped: {dataset['scrape_info']['timestamp']}")
    
    analyze_tags(videos)
    analyze_descriptions(videos)
    analyze_temporal_patterns(videos)
    suggest_authority_records(videos)
    
    print(f"\n🎯 SCHEMA RECOMMENDATIONS:")
    print(f"   ✅ Add activities table (15+ distinct activity types)")
    print(f"   ✅ Add gear/equipment table (10+ gear categories)")
    print(f"   ✅ Add tag_authority table (1000+ tags need normalization)")
    print(f"   ✅ Add user/editor tracking (created_by, updated_by fields)")
    print(f"   ✅ Add temporal analysis fields (upload_year, upload_month)")

if __name__ == "__main__":
    main()
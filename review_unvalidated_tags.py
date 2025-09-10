#!/usr/bin/env python3
"""
Systematically review unvalidated tags to identify candidates for new authorities.
This helps identify patterns and frequently used tags that should become authorities.
"""

import sqlite3
import json
from collections import Counter, defaultdict

def analyze_unvalidated_tags():
    """Analyze unvalidated tags in the database for authority creation opportunities"""
    
    print("🔍 UNVALIDATED TAG ANALYSIS")
    print("=" * 50)
    
    # Connect to database
    conn = sqlite3.connect('posa_wiki.db')
    cursor = conn.cursor()
    
    # Get all unvalidated tags
    cursor.execute('SELECT unvalidated_tags FROM videos WHERE unvalidated_tags IS NOT NULL AND unvalidated_tags != "[]"')
    all_unvalidated = cursor.fetchall()
    
    # Flatten and count all unvalidated tags
    tag_counter = Counter()
    tag_contexts = defaultdict(list)  # Store which videos use each tag
    
    for (unval_json,) in all_unvalidated:
        unval_tags = json.loads(unval_json)
        for tag in unval_tags:
            tag_lower = tag.lower().strip()
            tag_counter[tag_lower] += 1
            
            # Get video context for this tag
            cursor.execute('SELECT video_id, title FROM videos WHERE unvalidated_tags LIKE ?', (f'%{tag}%',))
            contexts = cursor.fetchall()
            tag_contexts[tag_lower].extend(contexts)
    
    print(f"📊 Found {len(tag_counter)} unique unvalidated tags")
    print(f"   Total unvalidated tag instances: {sum(tag_counter.values())}")
    
    # Categorize by frequency
    high_frequency = [(tag, count) for tag, count in tag_counter.items() if count >= 15]
    medium_frequency = [(tag, count) for tag, count in tag_counter.items() if 5 <= count < 15]
    low_frequency = [(tag, count) for tag, count in tag_counter.items() if count < 5]
    
    print(f"\n🎯 HIGH FREQUENCY TAGS (15+ uses) - Should definitely become authorities:")
    for tag, count in sorted(high_frequency, key=lambda x: x[1], reverse=True):
        print(f"   {tag}: {count} uses")
        # Show a few example videos
        example_videos = list(set(tag_contexts[tag]))[:3]
        for video_id, title in example_videos:
            print(f"     → {video_id}: {title[:50]}...")
        print()
    
    print(f"\n📝 MEDIUM FREQUENCY TAGS (5-14 uses) - Good candidates:")
    for tag, count in sorted(medium_frequency, key=lambda x: x[1], reverse=True):
        print(f"   {tag}: {count} uses")
    
    print(f"\n📋 LOW FREQUENCY TAGS (1-4 uses) - {len(low_frequency)} total")
    print("   (Not showing individual items - likely too specific for authorities)")
    
    
    conn.close()
    
    return {
        'high_frequency': high_frequency,
        'medium_frequency': medium_frequency,
        'low_frequency': low_frequency
    }

if __name__ == "__main__":
    results = analyze_unvalidated_tags()
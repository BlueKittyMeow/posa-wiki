#!/usr/bin/env python3
"""
Create tag authority records from the top 50 most common tags.
This will be our canonical vocabulary with aliases/variants.
"""

import json
from collections import Counter

def load_dataset():
    with open('full_channel_scrape_20250902_142647.json', 'r') as f:
        return json.load(f)

def generate_tag_authorities():
    """Generate canonical tag authorities with aliases"""
    
    # Manual curation of top tags into canonical forms
    tag_authorities = [
        {
            "canonical_name": "Dogs",
            "category": "subject", 
            "aliases": ["dog", "dogs", "doggy", "good dog"],
            "description": "Content featuring dogs as primary subjects"
        },
        {
            "canonical_name": "Wilderness", 
            "category": "location_type",
            "aliases": ["wilderness", "wilderness area", "wild", "backcountry"],
            "description": "Remote, undeveloped natural areas"
        },
        {
            "canonical_name": "Bushcraft",
            "category": "activity",
            "aliases": ["bushcraft", "bushcrafting", "bushcrafter", "bushcraft skills", "bushcraft camp"],
            "description": "Traditional outdoor skills and self-reliance techniques"
        },
        {
            "canonical_name": "Camping",
            "category": "activity", 
            "aliases": ["camping", "camp", "campout", "wild camp", "wild camping"],
            "description": "Overnight outdoor accommodation"
        },
        {
            "canonical_name": "Campfire Cooking",
            "category": "activity",
            "aliases": ["campfire cooking", "cooking", "campfire food", "fire cooking", "camp food"],
            "description": "Preparing food over open fires"
        },
        {
            "canonical_name": "Campfire",
            "category": "equipment",
            "aliases": ["campfire", "fire", "fire making"],
            "description": "Open fires for cooking and warmth"
        },
        {
            "canonical_name": "Winter Camping", 
            "category": "activity",
            "aliases": ["winter camping", "winter camp", "cold camping", "winter"],
            "description": "Camping in winter conditions"
        },
        {
            "canonical_name": "Boundary Waters Canoe Area",
            "category": "location",
            "aliases": ["bwca", "bwcaw", "boundary waters", "boundary waters canoe area"],
            "description": "Wilderness area in Minnesota/Ontario border region"
        },
        {
            "canonical_name": "Dog Training",
            "category": "activity", 
            "aliases": ["dog training", "camping dog"],
            "description": "Training dogs for outdoor activities"
        },
        {
            "canonical_name": "Fishing",
            "category": "activity",
            "aliases": ["fishing", "fish", "catch and cook", "catch and release", "trout fishing"],
            "description": "Recreational angling activities"
        },
        {
            "canonical_name": "Backpacking",
            "category": "activity",
            "aliases": ["backpacking", "backpacker", "backpack camping"],
            "description": "Multi-day hiking with overnight gear"
        },
        {
            "canonical_name": "Adventure",
            "category": "content_type",
            "aliases": ["adventure", "adventurer"],
            "description": "Exciting outdoor experiences"
        },
        {
            "canonical_name": "Survival Skills",
            "category": "activity", 
            "aliases": ["survival", "survival skills", "survival food", "survival shelter"],
            "description": "Skills for surviving in challenging conditions"
        },
        {
            "canonical_name": "Forest",
            "category": "location_type",
            "aliases": ["forest", "woods"],
            "description": "Wooded natural areas"
        },
        {
            "canonical_name": "Canoe Camping",
            "category": "activity",
            "aliases": ["canoe camping", "canoe", "canoeing", "canoe trip", "paddle", "paddling"],
            "description": "Camping accessed by canoe travel"
        },
        {
            "canonical_name": "Gourmet Cooking",
            "category": "activity",
            "aliases": ["gourmet cooking", "gourmet", "gourmet food"],
            "description": "High-quality outdoor cooking"
        },
        {
            "canonical_name": "Nature",
            "category": "subject",
            "aliases": ["nature", "outdoors", "outdoor", "nature sounds"],
            "description": "Natural environments and phenomena"
        },
        {
            "canonical_name": "Fall Camping",
            "category": "activity",
            "aliases": ["fall camping", "fall"],
            "description": "Camping during autumn season"
        },
        {
            "canonical_name": "Spring Camping", 
            "category": "activity",
            "aliases": ["spring camping", "spring"],
            "description": "Camping during spring season"
        },
        {
            "canonical_name": "Michigan",
            "category": "location",
            "aliases": ["michigan"],
            "description": "U.S. state in Great Lakes region"
        }
    ]
    
    return tag_authorities

def create_mapping_analysis(dataset, authorities):
    """Analyze how well our authorities cover the existing tags"""
    
    # Get all tags from dataset
    all_tags = []
    for video in dataset['videos']:
        tags = video.get('snippet', {}).get('tags', [])
        all_tags.extend([tag.lower() for tag in tags])
    
    tag_counts = Counter(all_tags)
    
    # Create alias lookup
    alias_to_authority = {}
    for auth in authorities:
        canonical = auth['canonical_name']
        for alias in auth['aliases']:
            alias_to_authority[alias.lower()] = canonical
    
    # Analyze coverage
    mapped_tags = 0
    unmapped_tags = []
    total_tag_instances = 0
    mapped_instances = 0
    
    for tag, count in tag_counts.items():
        total_tag_instances += count
        if tag in alias_to_authority:
            mapped_tags += 1
            mapped_instances += count
        else:
            if count >= 5:  # Only care about frequently used unmapped tags
                unmapped_tags.append((tag, count))
    
    print(f"📊 TAG AUTHORITY COVERAGE ANALYSIS")
    print(f"   Total unique tags: {len(tag_counts)}")
    print(f"   Tags mapped to authorities: {mapped_tags}")
    print(f"   Coverage: {mapped_tags/len(tag_counts)*100:.1f}% of unique tags")
    print(f"   Instance coverage: {mapped_instances/total_tag_instances*100:.1f}% of tag uses")
    
    print(f"\n🔍 TOP UNMAPPED TAGS (5+ uses):")
    for tag, count in sorted(unmapped_tags, key=lambda x: x[1], reverse=True)[:20]:
        print(f"     {tag}: {count}")
    
    return alias_to_authority, unmapped_tags

def main():
    print("🏷️  TAG AUTHORITY SYSTEM GENERATOR")
    print("=" * 50)
    
    dataset = load_dataset()
    authorities = generate_tag_authorities()
    
    print(f"Generated {len(authorities)} canonical tag authorities:")
    for auth in authorities[:5]:  # Show first 5
        print(f"  • {auth['canonical_name']} ({auth['category']})")
        print(f"    Aliases: {', '.join(auth['aliases'][:3])}...")
    
    # Analysis
    alias_mapping, unmapped = create_mapping_analysis(dataset, authorities)
    
    # Save authority records
    output = {
        'authorities': authorities,
        'analysis': {
            'total_authorities': len(authorities),
            'total_aliases': sum(len(a['aliases']) for a in authorities),
            'unmapped_frequent_tags': unmapped[:50]  # Top 50 unmapped
        }
    }
    
    with open('tag_authority_system.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n💾 Tag authority system saved to tag_authority_system.json")
    print(f"    Ready for database implementation!")

if __name__ == "__main__":
    main()
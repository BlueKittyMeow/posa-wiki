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
            "canonical_name": "Bushcraft",
            "category": "activity",
            "aliases": ["bushcraft", "bushcrafting", "bushcrafter", "bushcraft skills", "bushcraft camp", "bushcraft shelter", "bushcraft cooking"],
            "description": "Traditional outdoor skills and self-reliance techniques"
        },
        {
            "canonical_name": "Camping",
            "category": "activity", 
            "aliases": ["camping", "camp", "campout", "wild camp", "wild camping", "going camping"],
            "description": "Overnight outdoor accommodation"
        },
        {
            "canonical_name": "Campfire Cooking",
            "category": "activity",
            "aliases": ["campfire cooking", "cooking", "campfire food", "fire cooking", "camp food", "bushcraft cooking"],
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
            "aliases": ["winter camping", "winter camp", "cold camping", "winter", "winter time"],
            "description": "Camping in winter conditions"
        },
        {
            "canonical_name": "Spring Camping",
            "category": "activity", 
            "aliases": ["spring camping", "spring camp", "spring"],
            "description": "Camping in spring conditions"
        },
        {
            "canonical_name": "Fall Camping",
            "category": "activity",
            "aliases": ["fall camping", "fall camp", "autumn camping", "fall"],
            "description": "Camping in fall/autumn conditions"
        },
        {
            "canonical_name": "Survival Structures",
            "category": "activity",
            "aliases": ["lean to", "lean-to", "quinzhee", "quinzee", "shelter", "survival shelter", "bushcraft shelter"],
            "description": "Building emergency or primitive shelters"
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
            "aliases": ["fishing", "fish", "catch and cook", "catch and release", "trout fishing", "catching fish", "fisherman"],
            "description": "Recreational angling activities"
        },
        {
            "canonical_name": "Backpacking",
            "category": "activity",
            "aliases": ["backpacking", "backpacker", "backpack camping", "backpack"],
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
            "aliases": ["canoe camping", "canoe", "canoeing", "canoe trip", "paddle", "paddling", "canoe paddle"],
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
            "aliases": ["nature", "outdoors", "outdoor", "nature sounds", "outside"],
            "description": "Natural environments and phenomena"
        },
        {
            "canonical_name": "Michigan",
            "category": "location",
            "aliases": ["michigan"],
            "description": "U.S. state in Great Lakes region"
        },
        {
            "canonical_name": "Giveaways",
            "category": "content_type",
            "aliases": ["giveaway", "giveaways", "give away", "subscriber giveaway", "subscribers giveaway"],
            "description": "Subscriber milestone giveaway videos"
        },
        {
            "canonical_name": "Unboxing",
            "category": "content_type", 
            "aliases": ["unboxing", "unbox", "unboxing gifts"],
            "description": "Fan mail and gear unboxing videos"
        },
        {
            "canonical_name": "Channel Updates",
            "category": "content_type",
            "aliases": ["update", "channel update", "channel"],
            "description": "Channel status and personal update videos"
        },
        {
            "canonical_name": "Anniversary Content",
            "category": "content_type",
            "aliases": ["anniversary"],
            "description": "Channel anniversary and milestone celebration videos"
        },
        {
            "canonical_name": "Christmas Content",
            "category": "content_type",
            "aliases": ["christmas", "merry christmas", "santa", "santa clause"],
            "description": "Christmas and holiday themed videos"
        },
        {
            "canonical_name": "Subscriber Content",
            "category": "content_type",
            "aliases": ["subscribers", "subscriber"],
            "description": "Content focused on subscriber engagement and community"
        },
        
        # Weather Authorities
        {
            "canonical_name": "Snow Conditions", 
            "category": "weather",
            "aliases": ["snow", "snowstorm", "snowing", "snowy", "snow storm", "winter storm", "snowstorm camping", "camping in a snowstorm", "winter weather", "snow camping", "blizzard", "camping in a blizzard"],
            "description": "Snow and winter storm weather conditions including blizzards"
        },
        {
            "canonical_name": "Rain Conditions",
            "category": "weather", 
            "aliases": ["rain", "raining", "rainstorm", "storm", "thunderstorm", "camping in the rain", "fire in the rain", "severe weather"],
            "description": "Rain and storm weather conditions"
        },
        {
            "canonical_name": "Cold Conditions",
            "category": "weather",
            "aliases": ["cold", "frigid", "freezing", "cold weather"],
            "description": "Cold temperature weather conditions"
        },
        
        # Additional Locations
        {
            "canonical_name": "Canada",
            "category": "location",
            "aliases": ["canada"],
            "description": "Canadian wilderness areas and adventures"
        },
        {
            "canonical_name": "Montana", 
            "category": "location",
            "aliases": ["montana", "montana wilderness"],
            "description": "Montana state adventures (often with friends)"
        },
        
        # Additional Activities
        {
            "canonical_name": "Hiking",
            "category": "activity",
            "aliases": ["hiking", "hike", "hiker", "hike and cook"],
            "description": "Day hiking and walking adventures"
        },
        {
            "canonical_name": "Backcountry Camping",
            "category": "activity",
            "aliases": ["backcountry camping", "wilderness camping", "remote camping", "wilderness", "wilderness area", "wild", "backcountry", "wilderness adventure", "camping in the wilderness"],
            "description": "Remote wilderness camping and activities in undeveloped natural areas"
        },
        {
            "canonical_name": "Overnight Camping",
            "category": "activity",
            "aliases": ["overnight", "overnight camping"],
            "description": "Single night camping experiences"
        },
        {
            "canonical_name": "Summer Camping",
            "category": "activity",
            "aliases": ["summer camping", "summer"],
            "description": "Camping during summer season"
        },
        {
            "canonical_name": "Snowshoeing",
            "category": "activity", 
            "aliases": ["snowshoeing", "snowshoe", "snow shoeing", "snow shoe", "snowshoes", "showshoeing"],
            "description": "Winter snowshoe hiking adventures"
        },
        {
            "canonical_name": "Fire Skills",
            "category": "activity",
            "aliases": ["fire skills", "fire skill", "firesteel"],
            "description": "Fire making and fire management techniques"
        },
        
        # Content Types
        {
            "canonical_name": "Humor Content",
            "category": "content_type",
            "aliases": ["funny", "hilarious", "silly", "funny dog", "silly dog", "silly dogs", "fun", "entertaining"],
            "description": "Comedic and entertaining video content"
        },
        {
            "canonical_name": "Outdoorsman Content",
            "category": "content_type",
            "aliases": ["outdoorsman", "woodsman", "camper", "outdoors"],
            "description": "Content focused on outdoor lifestyle and skills"
        },
        {
            "canonical_name": "ASMR Content", 
            "category": "content_type",
            "aliases": ["asmr", "asmr fire", "asmr nature", "relaxing sounds", "fire asmr", "relaxation", "meditation"],
            "description": "Relaxing audio content for ASMR experience"
        },
        {
            "canonical_name": "How-To Content",
            "category": "content_type",
            "aliases": ["how to camp", "how to fish", "camping skills", "outdoor skills", "knife skills", "how to winter camp", "how to start a fire", "educational"],
            "description": "Educational and instructional outdoor content"
        },
        {
            "canonical_name": "Food Content",
            "category": "content_type", 
            "aliases": ["food", "meal", "dinner", "cooking outdoors", "meal prep", "delicious", "steak", "pasta"],
            "description": "Food preparation and cooking content"
        },
        
        # Equipment/Specialized
        {
            "canonical_name": "Hot Tent Camping",
            "category": "activity",
            "aliases": ["hot tent", "wood burning stove"],
            "description": "Winter camping with heated tent shelters"
        },
        {
            "canonical_name": "Tent Camping",
            "category": "equipment",
            "aliases": ["tent", "tents"],
            "description": "Camping with tent shelters"
        },
        
        # Series/Show Content
        {
            "canonical_name": "Unsuccessful Fishing Show",
            "category": "content_type",
            "aliases": ["unsuccessful fishing show", "ufs", "fishing show"],
            "description": "Episodic fishing adventure series"
        },
        
        # Dogs
        {
            "canonical_name": "Monty",
            "category": "character",
            "aliases": ["monty", "monty dog", "monty the collie"],
            "description": "Matthew's primary dog companion, Rough Collie"
        },
        {
            "canonical_name": "Rueger", 
            "category": "character",
            "aliases": ["rueger", "rueger dog"],
            "description": "Matthew's dog companion, mixed breed"
        },
        
        # People
        {
            "canonical_name": "Matthew Posa",
            "category": "person", 
            "aliases": ["matthew posa"],
            "description": "Matthew Posa, channel creator and host"
        },
        {
            "canonical_name": "Lucas",
            "category": "person", 
            "aliases": ["lucas", "captain teeny trout", "teeny trout"],
            "description": "Lucas Mathis, friend and fellow outdoor content creator"
        },
        {
            "canonical_name": "Funk",
            "category": "person", 
            "aliases": ["funk"],
            "description": "Friend and outdoor adventure companion"
        },
        {
            "canonical_name": "Erin (Friend)",
            "category": "person", 
            "aliases": ["erin"],
            "description": "Friend who appears in some adventures"
        },
        {
            "canonical_name": "Jake",
            "category": "person", 
            "aliases": ["jake"],
            "description": "Friend and outdoor adventure companion"
        },
        {
            "canonical_name": "Ken",
            "category": "person", 
            "aliases": ["ken", "chainsaw ken"],
            "description": "Friend and outdoor adventure companion"
        },
        
        # Breeds
        {
            "canonical_name": "Rough Collie",
            "category": "breed",
            "aliases": ["rough collie", "collie"],
            "description": "Dog breed - long-haired herding breed"
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
    
    # Create alias lookup with multi-authority support
    alias_to_authority = {}
    for auth in authorities:
        canonical = auth['canonical_name']
        for alias in auth['aliases']:
            alias_lower = alias.lower()
            
            # Support multiple authorities per alias
            if alias_lower in alias_to_authority:
                # Convert to list if not already
                if isinstance(alias_to_authority[alias_lower], str):
                    alias_to_authority[alias_lower] = [alias_to_authority[alias_lower]]
                # Add new authority
                alias_to_authority[alias_lower].append(canonical)
            else:
                alias_to_authority[alias_lower] = canonical
    
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
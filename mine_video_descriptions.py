#!/usr/bin/env python3
"""
Mine video descriptions for people and pet mentions.
Uses NLP patterns to identify who appears in videos with confidence scoring.
"""

import sqlite3
import re
import json
from collections import defaultdict, Counter

def load_known_entities():
    """Load known people, dogs, and common names from our data"""
    
    # Known people from our authorities and database
    known_people = {
        'matthew': ['matthew', 'matt', 'posa', 'matthew posa'],
        'lucas': ['lucas', 'lucas mathis', 'captain teeny trout', 'teeny trout', 'capt teeny trout', 'captain tiny trout'],
        'funk': ['funk', 'funky jugs', 'funkyjugs'],
        'erin': ['erin'],
        'ken': ['ken', 'chainsaw ken', 'buddy ken'],
        'jake': ['jake', 'ski guy jake', 'jake ski guy'],
        'mom': ['mom', 'mother', 'my mom'],
        'dad': ['dad', 'father', 'my dad'],
        'brother': ['brother', 'my brother']
    }
    
    # Known dogs
    known_dogs = {
        'monty': ['monty'],
        'rueger': ['rueger'],
        'frodo': ['frodo']  # From your mention
    }
    
    # Family/relationship terms
    family_terms = ['mom', 'dad', 'mother', 'father', 'brother', 'sister', 'wife', 'girlfriend', 
                   'boyfriend', 'family', 'parents', 'son', 'daughter', 'friend', 'buddy', 'pal']
    
    # Common first names to watch for
    common_names = ['mike', 'john', 'sarah', 'sara', 'chris', 'dave', 'david', 'steve', 'ryan', 
                   'tyler', 'alex', 'sam', 'nick', 'ben', 'tom', 'james', 'dan', 'daniel',
                   'kevin', 'brian', 'mark', 'paul', 'scott', 'jeff', 'tim', 'tony', 'joe',
                   'josh', 'kyle', 'jason', 'adam', 'brandon', 'jeremy', 'aaron', 'andrew']
    
    return known_people, known_dogs, family_terms, common_names

def analyze_description(description, known_people, known_dogs, family_terms, common_names):
    """Analyze a video description for people/pet mentions with confidence scoring"""
    
    if not description:
        return [], [], []
    
    desc_lower = description.lower()
    
    high_confidence = []
    medium_confidence = []
    low_confidence = []
    
    # HIGH CONFIDENCE: Explicit "with X" patterns
    with_patterns = [
        r'with\s+(\w+)',
        r'and\s+(\w+)\s+(?:went|come|came|join)',
        r'(\w+)\s+and\s+i\s+(?:went|head|travel)',
        r'me\s+and\s+(\w+)',
        r'(\w+)\s+joins?\s+me',
        r'(\w+),?\s+and\s+i\s+',
        r'i\s+and\s+(\w+)\s+',
        r'(\w+)\s+tagged\s+along',
        r'brought\s+(\w+)\s+',
        r'(\w+)\s+decided\s+to\s+(?:come|join)'
    ]
    
    for pattern in with_patterns:
        matches = re.findall(pattern, desc_lower)
        for match in matches:
            # Check if it's a known entity
            for person, aliases in known_people.items():
                if match in aliases:
                    high_confidence.append((person, 'person', f'with {match}'))
                    break
            for dog, aliases in known_dogs.items():
                if match in aliases:
                    high_confidence.append((dog, 'dog', f'with {match}'))
                    break
    
    # Additional multi-word "with" patterns
    multi_word_with_patterns = [
        r'with\s+((?:\w+\s+){1,3}\w+)',  # Capture 2-4 words after "with"
        r'and\s+((?:\w+\s+){1,3}\w+)\s+(?:went|come|came|join)',
    ]
    
    for pattern in multi_word_with_patterns:
        matches = re.findall(pattern, desc_lower)
        for match in matches:
            match = match.strip()
            # Check against our multi-word aliases
            for person, aliases in known_people.items():
                for alias in aliases:
                    if len(alias.split()) > 1 and alias in match:
                        high_confidence.append((person, 'person', f'with {match}'))
                        break
    
    # HIGH CONFIDENCE: Known entities mentioned (improved multi-word support)
    for person, aliases in known_people.items():
        for alias in aliases:
            # For multi-word aliases, just check if they appear in the description
            if len(alias.split()) > 1:
                if alias in desc_lower:
                    high_confidence.append((person, 'person', f'mentioned: {alias}'))
            else:
                # For single words, use word boundaries
                if re.search(r'\\b' + re.escape(alias) + r'\\b', desc_lower):
                    high_confidence.append((person, 'person', f'mentioned: {alias}'))
    
    for dog, aliases in known_dogs.items():
        for alias in aliases:
            if len(alias.split()) > 1:
                if alias in desc_lower:
                    high_confidence.append((dog, 'dog', f'mentioned: {alias}'))
            else:
                if re.search(r'\\b' + re.escape(alias) + r'\\b', desc_lower):
                    high_confidence.append((dog, 'dog', f'mentioned: {alias}'))
    
    # MEDIUM CONFIDENCE: Family terms
    for term in family_terms:
        if re.search(r'\\b' + term + r'\\b', desc_lower):
            medium_confidence.append((term, 'family', f'family term: {term}'))
    
    # LOW CONFIDENCE: Potential names (proper nouns that could be people)
    words = re.findall(r'\\b[A-Z][a-z]+\\b', description)
    for word in words:
        word_lower = word.lower()
        # Skip obvious non-names
        if word_lower not in ['the', 'and', 'with', 'for', 'you', 'this', 'that', 'they', 'them',
                             'camping', 'fishing', 'winter', 'summer', 'spring', 'fall', 'snow',
                             'water', 'lake', 'river', 'forest', 'tent', 'fire', 'food', 'cooking']:
            if word_lower in common_names:
                low_confidence.append((word_lower, 'potential_person', f'possible name: {word}'))
    
    # Remove duplicates while preserving order
    high_confidence = list(dict.fromkeys(high_confidence))
    medium_confidence = list(dict.fromkeys(medium_confidence))
    low_confidence = list(dict.fromkeys(low_confidence))
    
    return high_confidence, medium_confidence, low_confidence

def search_specific_incidents():
    """Search for specific incidents mentioned by user"""
    
    conn = sqlite3.connect('posa_wiki.db')
    cursor = conn.cursor()
    
    print("🔍 SEARCHING FOR SPECIFIC INCIDENTS:")
    print("=" * 60)
    
    # Search for canoe flipping incident with Erin, Funk, Rueger, Monty
    cursor.execute('''
    SELECT video_id, title, description 
    FROM videos 
    WHERE description LIKE '%canoe%' 
    AND (description LIKE '%flip%' OR description LIKE '%tip%' OR description LIKE '%choppy%' OR description LIKE '%rough%')
    ''')
    
    canoe_incidents = cursor.fetchall()
    if canoe_incidents:
        print("🛶 POTENTIAL CANOE FLIPPING INCIDENTS:")
        for video_id, title, desc in canoe_incidents:
            print(f"  {video_id}: {title}")
            if any(name in desc.lower() for name in ['erin', 'funk', 'rueger', 'monty']):
                print(f"    ✅ Contains: {[name for name in ['erin', 'funk', 'rueger', 'monty'] if name in desc.lower()]}")
            print(f"    Description snippet: {desc[:100]}...")
            print()
    
    # Search for extreme cold videos (-40 degrees)
    cursor.execute('''
    SELECT video_id, title, description 
    FROM videos 
    WHERE description LIKE '%40%' 
    AND (description LIKE '%below%' OR description LIKE '%minus%' OR description LIKE '%-40%' OR description LIKE '%cold%')
    ''')
    
    cold_incidents = cursor.fetchall()
    if cold_incidents:
        print("🥶 POTENTIAL EXTREME COLD INCIDENTS:")
        for video_id, title, desc in cold_incidents:
            print(f"  {video_id}: {title}")
            if any(name in desc.lower() for name in ['ken', 'jake']):
                print(f"    ✅ Contains: {[name for name in ['ken', 'jake'] if name in desc.lower()]}")
            print(f"    Description snippet: {desc[:100]}...")
            print()
    
    conn.close()

def mine_video_descriptions():
    """Mine all video descriptions for people/pet mentions"""
    
    print("🔍 MINING VIDEO DESCRIPTIONS FOR PEOPLE/PET MENTIONS")
    print("=" * 60)
    
    # Load known entities
    known_people, known_dogs, family_terms, common_names = load_known_entities()
    
    # Connect to database
    conn = sqlite3.connect('posa_wiki.db')
    cursor = conn.cursor()
    
    # Get all videos with descriptions
    cursor.execute('SELECT video_id, title, description FROM videos WHERE description IS NOT NULL')
    videos = cursor.fetchall()
    
    print(f"📊 Analyzing {len(videos)} videos with descriptions...")
    
    # Track results
    high_confidence_results = []
    medium_confidence_results = []
    low_confidence_results = []
    
    entity_stats = defaultdict(int)
    
    for video_id, title, description in videos:
        high, medium, low = analyze_description(description, known_people, known_dogs, family_terms, common_names)
        
        if high:
            high_confidence_results.append((video_id, title, high))
            for entity, entity_type, context in high:
                entity_stats[f"{entity} ({entity_type})"] += 1
        
        if medium:
            medium_confidence_results.append((video_id, title, medium))
        
        if low:
            low_confidence_results.append((video_id, title, low))
    
    # Print results
    print(f"\\n🎯 HIGH CONFIDENCE MATCHES ({len(high_confidence_results)} videos):")
    print("=" * 60)
    
    for video_id, title, entities in high_confidence_results[:20]:  # Show first 20
        print(f"\\n{video_id}: {title[:50]}...")
        for entity, entity_type, context in entities:
            print(f"  → {entity} ({entity_type}): {context}")
    
    if len(high_confidence_results) > 20:
        print(f"  ... and {len(high_confidence_results) - 20} more videos")
    
    print(f"\\n📊 ENTITY FREQUENCY (High Confidence):")
    for entity, count in sorted(entity_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {entity:20} {count:3} videos")
    
    print(f"\\n🤔 MEDIUM CONFIDENCE - NEEDS REVIEW ({len(medium_confidence_results)} videos):")
    print("=" * 60)
    
    for video_id, title, entities in medium_confidence_results[:10]:  # Show first 10
        print(f"\\n{video_id}: {title[:50]}...")
        for entity, entity_type, context in entities:
            print(f"  → {entity} ({entity_type}): {context}")
    
    if len(medium_confidence_results) > 10:
        print(f"  ... and {len(medium_confidence_results) - 10} more videos")
    
    print(f"\\n❓ LOW CONFIDENCE - MANUAL REVIEW NEEDED ({len(low_confidence_results)} videos):")
    print("   (Showing summary of potential names found)")
    
    # Summarize low confidence findings
    low_conf_names = defaultdict(int)
    for video_id, title, entities in low_confidence_results:
        for entity, entity_type, context in entities:
            low_conf_names[entity] += 1
    
    for name, count in sorted(low_conf_names.items(), key=lambda x: x[1], reverse=True)[:15]:
        print(f"  {name:15} {count:3} videos")
    
    # Save detailed results to files for review
    results = {
        'high_confidence': high_confidence_results,
        'medium_confidence': medium_confidence_results, 
        'low_confidence': low_confidence_results,
        'entity_stats': dict(entity_stats)
    }
    
    with open('video_description_mining_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\\n💾 Detailed results saved to video_description_mining_results.json")
    print(f"\\n🎯 NEXT STEPS:")
    print(f"   1. Review high confidence matches - these look very accurate")
    print(f"   2. Check medium confidence family terms")
    print(f"   3. Manually review low confidence potential names")
    print(f"   4. Confirm which entities should be added to people/dogs tables")
    
    conn.close()

if __name__ == "__main__":
    search_specific_incidents()
    print("\n" + "=" * 80 + "\n")
    mine_video_descriptions()
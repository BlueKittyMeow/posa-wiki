#!/usr/bin/env python3
"""
Re-validate all database tags with the updated authority system.
This will catch tags like 'canada', 'asmr', etc. that should now be validated.
"""

import sqlite3
import json
from datetime import datetime

def load_tag_authorities():
    """Load current tag authority system with multi-authority support"""
    with open('tag_authority_system.json', 'r') as f:
        data = json.load(f)
    
    alias_to_authority = {}
    for auth in data['authorities']:
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
    
    # Count multi-authority mappings
    multi_mappings = sum(1 for v in alias_to_authority.values() if isinstance(v, list))
    print(f"📋 Loaded {len(data['authorities'])} authorities with {len(alias_to_authority)} aliases ({multi_mappings} multi-authority mappings)")
    return alias_to_authority

def validate_tags(video_tags, alias_to_authority):
    """Separate tags into validated and unvalidated arrays with multi-authority support"""
    if not video_tags:
        return [], []
    
    validated_tags = []
    unvalidated_tags = []
    
    for tag in video_tags:
        tag_lower = tag.lower().strip()
        
        if tag_lower in alias_to_authority:
            authorities = alias_to_authority[tag_lower]
            
            # Handle both single and multiple authorities
            if isinstance(authorities, str):
                authorities = [authorities]
                
            for authority in authorities:
                if authority not in validated_tags:
                    validated_tags.append(authority)
        else:
            if tag not in unvalidated_tags:
                unvalidated_tags.append(tag)
    
    return validated_tags, unvalidated_tags

def revalidate_all_videos():
    """Re-validate all videos with updated authority system"""
    
    print("🔄 RE-VALIDATING ALL VIDEO TAGS")
    print("=" * 50)
    
    # Load updated authorities
    alias_to_authority = load_tag_authorities()
    
    # Connect to database
    conn = sqlite3.connect('posa_wiki.db')
    cursor = conn.cursor()
    
    # Get all videos with their original YouTube tags
    cursor.execute('SELECT video_id, youtube_tags FROM videos WHERE youtube_tags IS NOT NULL AND youtube_tags != "[]"')
    all_videos = cursor.fetchall()
    
    print(f"📊 Re-validating {len(all_videos)} videos with tags...")
    
    updated_count = 0
    stats = {
        'total_videos': len(all_videos),
        'videos_updated': 0,
        'old_validated_total': 0,
        'new_validated_total': 0,
        'old_unvalidated_total': 0,
        'new_unvalidated_total': 0
    }
    
    for video_id, youtube_tags_json in all_videos:
        # Get original YouTube tags
        original_tags = json.loads(youtube_tags_json)
        
        # Get current validation
        cursor.execute('SELECT validated_tags, unvalidated_tags FROM videos WHERE video_id = ?', (video_id,))
        current_val_json, current_unval_json = cursor.fetchone()
        
        current_validated = json.loads(current_val_json) if current_val_json else []
        current_unvalidated = json.loads(current_unval_json) if current_unval_json else []
        
        # Re-validate with updated authorities
        new_validated, new_unvalidated = validate_tags(original_tags, alias_to_authority)
        
        # Update stats
        stats['old_validated_total'] += len(current_validated)
        stats['new_validated_total'] += len(new_validated)
        stats['old_unvalidated_total'] += len(current_unvalidated)
        stats['new_unvalidated_total'] += len(new_unvalidated)
        
        # Check if validation changed
        if (set(new_validated) != set(current_validated) or 
            set(new_unvalidated) != set(current_unvalidated)):
            
            # Update database
            cursor.execute('''
            UPDATE videos 
            SET validated_tags = ?, unvalidated_tags = ?, updated_at = ?
            WHERE video_id = ?
            ''', (
                json.dumps(new_validated),
                json.dumps(new_unvalidated), 
                datetime.now().isoformat(),
                video_id
            ))
            
            updated_count += 1
            stats['videos_updated'] += 1
            
            # Show examples of improvements
            if updated_count <= 5:
                newly_validated = set(new_validated) - set(current_validated)
                if newly_validated:
                    print(f"  ✅ {video_id}: Added validated tags: {list(newly_validated)}")
    
    conn.commit()
    
    print(f"\\n📊 RE-VALIDATION COMPLETE!")
    print(f"   Videos processed: {stats['total_videos']}")
    print(f"   Videos updated: {stats['videos_updated']}")
    print(f"   Validated tags: {stats['old_validated_total']} → {stats['new_validated_total']} (+{stats['new_validated_total'] - stats['old_validated_total']})")
    print(f"   Unvalidated tags: {stats['old_unvalidated_total']} → {stats['new_unvalidated_total']} ({stats['new_unvalidated_total'] - stats['old_unvalidated_total']:+d})")
    
    # Calculate new coverage
    total_original_tags = stats['old_validated_total'] + stats['old_unvalidated_total']
    if total_original_tags > 0:
        old_coverage = (stats['old_validated_total'] / total_original_tags) * 100
        new_coverage = (stats['new_validated_total'] / (stats['new_validated_total'] + stats['new_unvalidated_total'])) * 100
        print(f"   Tag coverage: {old_coverage:.1f}% → {new_coverage:.1f}% (+{new_coverage - old_coverage:.1f}%)")
    
    # Show sample of newly caught tags
    print(f"\\n🎯 Sample newly validated tags in database:")
    cursor.execute('''
    SELECT video_id, title, validated_tags 
    FROM videos 
    WHERE (validated_tags LIKE '%Canada%' 
           OR validated_tags LIKE '%ASMR Content%'
           OR validated_tags LIKE '%How-To Content%')
    AND updated_at > datetime('now', '-1 hour')
    LIMIT 5
    ''')
    
    for video_id, title, val_tags in cursor.fetchall():
        val_list = json.loads(val_tags)
        relevant_tags = [tag for tag in val_list if tag in ['Canada', 'ASMR Content', 'How-To Content']]
        if relevant_tags:
            print(f"   {video_id}: {title[:40]}... → {relevant_tags}")
    
    conn.close()
    print(f"\\n🎉 Database re-validation complete with updated authorities!")

if __name__ == "__main__":
    revalidate_all_videos()
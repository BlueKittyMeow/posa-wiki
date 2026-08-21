#!/usr/bin/env python3
"""
Example of how multi-authority mapping could work for compound tags
"""

def generate_multi_authority_mapping(authorities):
    """Create mapping that supports multiple authorities per alias"""
    
    # Standard one-to-one mappings
    alias_to_authority = {}
    
    for auth in authorities:
        canonical = auth['canonical_name']
        for alias in auth['aliases']:
            alias_lower = alias.lower()
            
            # Check if this alias should map to multiple authorities
            if alias_lower in alias_to_authority:
                # Convert to list if not already
                if isinstance(alias_to_authority[alias_lower], str):
                    alias_to_authority[alias_lower] = [alias_to_authority[alias_lower]]
                # Add new authority
                alias_to_authority[alias_lower].append(canonical)
            else:
                alias_to_authority[alias_lower] = canonical
    
    return alias_to_authority

def validate_tags_multi_authority(video_tags, alias_to_authority):
    """Validate tags with support for multi-authority mapping"""
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

# Example usage:
example_authorities = [
    {
        "canonical_name": "Bushcraft",
        "aliases": ["bushcraft", "bushcraft shelter"]  # bushcraft shelter maps to Bushcraft
    },
    {
        "canonical_name": "Survival Structures", 
        "aliases": ["shelter", "bushcraft shelter"]   # bushcraft shelter ALSO maps to Survival Structures
    },
    {
        "canonical_name": "Adventure",
        "aliases": ["adventure", "wilderness adventure"]  # wilderness adventure maps to Adventure
    },
    {
        "canonical_name": "Wilderness",
        "aliases": ["wilderness", "wilderness adventure"]  # wilderness adventure ALSO maps to Wilderness
    }
]

if __name__ == "__main__":
    mapping = generate_multi_authority_mapping(example_authorities)
    
    print("Multi-authority mappings:")
    for alias, authorities in mapping.items():
        if isinstance(authorities, list):
            print(f"  '{alias}' → {authorities}")
    
    # Test validation
    test_tags = ["bushcraft shelter", "wilderness adventure", "camping"]
    validated, unvalidated = validate_tags_multi_authority(test_tags, mapping)
    
    print(f"\nTest tags: {test_tags}")
    print(f"Validated: {validated}")
    print(f"Unvalidated: {unvalidated}")
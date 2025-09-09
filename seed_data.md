# Initial Authority Records - Seed Data

## People
```sql
INSERT INTO people (canonical_name, aliases, bio, notes) VALUES
('Matthew Posa', '["Matt", "Matthew", "Posa"]', 'Content creator focused on wilderness camping and outdoor adventures with his dogs.', 'Primary channel owner'),
('Lucas Mathis', '["Lucas", "Teeny Trout", "Captain Teeny Trout"]', 'Frequent camping companion of Matthew Posa.', 'Has his own YouTube channel now');
```

## Dogs
```sql
INSERT INTO dogs (name, breed, breed_detail, color, description, notes) VALUES
('Monty', 'Collie', 'Rough', 'Sable', 'Matthew\'s adventure companion dog', 'Appears in early videos, very good camping dog'),
('Rueger', NULL, NULL, NULL, 'Matthew\'s second dog', 'Introduced as a puppy, referred to as Monty\'s "brother" but not biological siblings');
```

## Relationships
```sql
-- People-Dog ownership
INSERT INTO people_dog_relationships (person_id, dog_id, relationship_type, notes) VALUES
(1, 1, 'owner', 'Primary owner and adventure companion'),
(1, 2, 'owner', 'Primary owner, got as puppy');

-- Dog-Dog relationships  
INSERT INTO dog_dog_relationships (dog_id_1, dog_id_2, relationship_type, relationship_detail, notes) VALUES
(1, 2, 'brothers', 'Not biological siblings but live together and are referred to as brothers', 'Social/household relationship, not genetic');

-- People-People relationships
INSERT INTO people_people_relationships (person_id, related_person_id, relationship_type, notes) VALUES
(1, 2, 'friend', 'Frequent camping companion, now has own YouTube channel');
```

## Locations (from early videos)
```sql
INSERT INTO locations (main_location, specific_location, location_type, description, notes) VALUES
('Boundary Waters Canoe Area', NULL, 'wilderness_area', 'Wilderness area on Minnesota-Canada border', 'Frequent filming location'),
('Isle Royale', NULL, 'national_park', 'National park in Lake Superior', 'Featured in otter encounter video'),
('Michigan', NULL, 'state', 'State where winter camping occurs', 'Various locations within state'),
('Nicaragua', NULL, 'country', 'Central American travel destination', 'Vacation/travel content');
```

## Notes
- This seed data comes from analysis of the first 10 videos
- Additional authority records will be added as more videos are processed
- Aliases arrays can be expanded as more name variations are discovered
- Relationship dates can be added when more precise timeline information becomes available
# Companion & People Data for Posa Wiki

## Core People Structure

### Primary Creators
- **Matthew Posa** (@MatthewPosa)
- **Lucas** (@LucasAndLayla)  

### Regular Companions
- **Funk** (Erin) - Partner/GF, primary camping companion
- **Erin** (Friend) - Different person from Funk, also named Erin (confusing!)

### Family Members
- **Matthew's Dad** 
- **Matthew's Mom**
- **Matthew's Brother**

### Friends & Occasional Companions  
- **Chainsaw Ken**
- **Jake Ski Guy**
- **[Other friends TBD during curation]**

## Video Experience Categories

### Solo Adventures
- Just Matthew (+ dogs)
- Different feel/pacing
- More introspective content

### Partner Adventures  
- Matthew + Funk
- Couple dynamics
- Shared experiences

### Friend Adventures
- Matthew + Lucas (most common friend pairing)
- Matthew + Chainsaw Ken
- Matthew + Jake Ski Guy
- Group dynamics

### Family Adventures
- Various combinations of family members
- Different tone than friend trips
- Generational perspectives

## Database Implementation

Using existing `people` table + `video_people` relationship table:

```sql
-- People entries
INSERT INTO people VALUES 
(1, 'Matthew Posa', '@MatthewPosa', 'https://youtube.com/@MatthewPosa', '["Captain Teeny Trout", "Teeny Trout"]', 'Primary creator', NULL),
(2, 'Funk', NULL, NULL, '["Erin"]', 'Partner/girlfriend, regular camping companion', NULL),
(3, 'Erin', NULL, NULL, '[]', 'Friend (different from Funk)', NULL),
(4, 'Lucas', '@LucasAndLayla', 'https://youtube.com/@LucasAndLayla', '[]', 'Friend and fellow creator', NULL);

-- Video relationships  
INSERT INTO video_people VALUES
('ABC123', 1, 'primary', 'Main creator'),
('ABC123', 2, 'companion', 'Camping partner'),
('DEF456', 1, 'primary', 'Solo trip'),
('GHI789', 1, 'primary', 'Main creator'),
('GHI789', 4, 'companion', 'Friend adventure');
```

## Filter Queries Enabled

**Solo adventures:**
```sql
SELECT v.* FROM videos v 
JOIN video_people vp ON v.video_id = vp.video_id 
WHERE vp.person_id = 1 AND vp.role = 'primary'
AND v.video_id NOT IN (
    SELECT video_id FROM video_people WHERE person_id != 1
);
```

**With Funk:**
```sql  
SELECT v.* FROM videos v
JOIN video_people vp1 ON v.video_id = vp1.video_id AND vp1.person_id = 1
JOIN video_people vp2 ON v.video_id = vp2.video_id AND vp2.person_id = 2;
```

**Family trips:**
```sql
SELECT v.* FROM videos v 
JOIN video_people vp ON v.video_id = vp.video_id
JOIN people p ON vp.person_id = p.person_id
WHERE p.canonical_name IN ('Matthew''s Dad', 'Matthew''s Mom', 'Matthew''s Brother');
```

This allows dynamic filtering/playlist creation based on companion combinations!
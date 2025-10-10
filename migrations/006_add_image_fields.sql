-- Migration 006: Add Image Fields and Privacy Controls
-- Adds photo storage and visibility controls to people and dogs tables

-- People table: Add photo fields and visibility control
ALTER TABLE people ADD COLUMN photo_url TEXT DEFAULT NULL;
ALTER TABLE people ADD COLUMN photo_local_path TEXT DEFAULT NULL;
ALTER TABLE people ADD COLUMN photo_visible BOOLEAN DEFAULT 1;

-- Dogs table: Add photo fields and visibility control
ALTER TABLE dogs ADD COLUMN photo_url TEXT DEFAULT NULL;
ALTER TABLE dogs ADD COLUMN photo_local_path TEXT DEFAULT NULL;
ALTER TABLE dogs ADD COLUMN photo_visible BOOLEAN DEFAULT 1;

-- Create indexes for photo queries (finding entities with/without photos)
CREATE INDEX IF NOT EXISTS idx_people_photo_visible ON people(photo_visible);
CREATE INDEX IF NOT EXISTS idx_dogs_photo_visible ON dogs(photo_visible);

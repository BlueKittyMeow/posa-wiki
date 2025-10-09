-- Migration 005: Add Soft Delete Support
-- Adds deleted_at and deleted_by columns to all major tables for soft delete functionality

-- People table
ALTER TABLE people ADD COLUMN deleted_at TEXT DEFAULT NULL;
ALTER TABLE people ADD COLUMN deleted_by INTEGER DEFAULT NULL REFERENCES users(user_id);

-- Dogs table
ALTER TABLE dogs ADD COLUMN deleted_at TEXT DEFAULT NULL;
ALTER TABLE dogs ADD COLUMN deleted_by INTEGER DEFAULT NULL REFERENCES users(user_id);

-- Videos table
ALTER TABLE videos ADD COLUMN deleted_at TEXT DEFAULT NULL;
ALTER TABLE videos ADD COLUMN deleted_by INTEGER DEFAULT NULL REFERENCES users(user_id);

-- Trips table (handles both trips and series)
ALTER TABLE trips ADD COLUMN deleted_at TEXT DEFAULT NULL;
ALTER TABLE trips ADD COLUMN deleted_by INTEGER DEFAULT NULL REFERENCES users(user_id);

-- Users table (for deactivating admin users)
ALTER TABLE users ADD COLUMN deleted_at TEXT DEFAULT NULL;
ALTER TABLE users ADD COLUMN deleted_by INTEGER DEFAULT NULL REFERENCES users(user_id);

-- Create indexes for query performance (filtering WHERE deleted_at IS NULL)
CREATE INDEX IF NOT EXISTS idx_people_deleted_at ON people(deleted_at);
CREATE INDEX IF NOT EXISTS idx_dogs_deleted_at ON dogs(deleted_at);
CREATE INDEX IF NOT EXISTS idx_videos_deleted_at ON videos(deleted_at);
CREATE INDEX IF NOT EXISTS idx_trips_deleted_at ON trips(deleted_at);
CREATE INDEX IF NOT EXISTS idx_users_deleted_at ON users(deleted_at);

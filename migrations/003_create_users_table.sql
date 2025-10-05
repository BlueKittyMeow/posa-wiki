-- Migration 003: Create users table for authentication
-- Phase 2A - Authentication Foundations

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'viewer' CHECK(role IN ('admin', 'editor', 'viewer')),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_login TEXT
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

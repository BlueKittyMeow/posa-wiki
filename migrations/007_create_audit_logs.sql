-- Migration 007: Create audit_logs table
-- Provides persistent audit trail for security-sensitive events.

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    severity TEXT NOT NULL,
    event_type TEXT NOT NULL,
    user_id INTEGER,
    ip_address TEXT,
    user_agent TEXT,
    resource_type TEXT,
    resource_id TEXT,
    details TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_logs(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_logs(resource_type, resource_id);

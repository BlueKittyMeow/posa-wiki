#!/usr/bin/env python3
"""Run database migration script"""
import sqlite3
import sys
from pathlib import Path

def run_migration(migration_file):
    """Execute a SQL migration file against the database"""
    db_path = Path('posa_wiki.db')
    migration_path = Path(migration_file)

    if not migration_path.exists():
        print(f"Error: Migration file {migration_file} not found")
        sys.exit(1)

    print(f"Running migration: {migration_path.name}")

    with open(migration_path) as f:
        sql = f.read()

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(sql)
        conn.commit()
        print(f"✓ Migration {migration_path.name} completed successfully")
    except sqlite3.Error as e:
        print(f"✗ Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python run_migration.py <migration_file>")
        sys.exit(1)

    run_migration(sys.argv[1])

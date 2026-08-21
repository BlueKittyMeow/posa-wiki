"""Quick diagnostic to confirm audit log writes."""
import os
import sqlite3
import time
from types import SimpleNamespace

import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import services.audit_log_service as audit

APP_CONFIG = SimpleNamespace(config={'DATABASE_PATH': 'posa_wiki.db'})

def main():
    audit.init_audit_logging(APP_CONFIG)
    audit.create_audit_log('diagnostic_test', details={'status': 'ok'})

    # Give the background listener a moment to flush the log entry.
    time.sleep(0.2)

    conn = sqlite3.connect(APP_CONFIG.config['DATABASE_PATH'])
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT event_type, details FROM audit_logs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if row is None:
        print("No audit log entry found. Ensure migration 007 has been applied.")
    else:
        print(dict(row))

if __name__ == '__main__':
    main()

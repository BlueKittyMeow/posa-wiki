"""Asynchronous audit logging service."""

from __future__ import annotations

import atexit
import json
import logging
import queue
import sqlite3
from datetime import datetime
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path
from typing import Any, Dict, Optional

from flask import has_request_context, request
from flask_login import current_user

# Queue-based logger configuration
_log_queue: queue.Queue = queue.Queue()
_queue_listener: Optional[QueueListener] = None

audit_logger = logging.getLogger('audit')
audit_logger.setLevel(logging.INFO)
audit_logger.propagate = False
audit_logger.addHandler(QueueHandler(_log_queue))


class SQLiteAuditHandler(logging.Handler):
    """Logging handler that persists audit events to SQLite."""

    def __init__(self, db_path: Path):
        super().__init__(level=logging.INFO)
        self.db_path = db_path

    def emit(self, record: logging.LogRecord) -> None:
        data = self._record_to_row(record)

        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """
                INSERT INTO audit_logs (
                    timestamp,
                    severity,
                    event_type,
                    user_id,
                    ip_address,
                    user_agent,
                    resource_type,
                    resource_id,
                    details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data['timestamp'],
                    data['severity'],
                    data['event_type'],
                    data['user_id'],
                    data['ip_address'],
                    data['user_agent'],
                    data['resource_type'],
                    data['resource_id'],
                    data['details_json']
                )
            )
            conn.commit()
        except sqlite3.Error as exc:
            logging.getLogger(__name__).error("Failed to write audit log: %s", exc)
        finally:
            conn.close()

    def _record_to_row(self, record: logging.LogRecord) -> Dict[str, Any]:
        timestamp = datetime.utcnow().isoformat()

        extra_details = getattr(record, 'details', None) or {}
        if not isinstance(extra_details, dict):
            extra_details = {'details': str(extra_details)}

        details = {'message': record.getMessage()}
        details.update(extra_details)

        return {
            'timestamp': timestamp,
            'severity': record.levelname,
            'event_type': getattr(record, 'event_type', 'unspecified'),
            'user_id': getattr(record, 'user_id', None),
            'ip_address': getattr(record, 'ip_address', None),
            'user_agent': getattr(record, 'user_agent', None),
            'resource_type': getattr(record, 'resource_type', None),
            'resource_id': getattr(record, 'resource_id', None),
            'details_json': json.dumps(details)
        }


def init_audit_logging(app) -> None:
    """Initialize audit logging queue listener."""
    global _queue_listener

    if _queue_listener:
        # Already initialized
        return

    db_path = Path(app.config['DATABASE_PATH'])

    # Ensure table exists (migration should create it, but fail-safe for dev/test)
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
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
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    handler = SQLiteAuditHandler(db_path)
    _queue_listener = QueueListener(_log_queue, handler)
    _queue_listener.start()

    @atexit.register
    def _shutdown_listener():
        if _queue_listener:
            _queue_listener.stop()


def redact_sensitive_fields(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Redact sensitive keys from a dictionary."""
    if not data:
        return data

    sensitive = {'password', 'password_hash', 'token', 'api_key', 'secret'}
    redacted = {}
    for key, value in data.items():
        if key.lower() in sensitive:
            redacted[key] = '[REDACTED]'
        else:
            redacted[key] = value
    return redacted


def create_audit_log(
    event_type: str,
    severity: str = 'INFO',
    resource_type: Optional[str] = None,
    resource_id: Optional[Any] = None,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Enqueue an audit log entry.

    Args:
        event_type: Event identifier, e.g., 'login_success'.
        severity: Logging severity level.
        resource_type: Associated resource type, e.g., 'user'.
        resource_id: Identifier of the resource.
        details: Additional metadata (will be JSON serialized).
    """
    extras = {
        'event_type': event_type,
        'resource_type': resource_type,
        'resource_id': resource_id,
        'details': redact_sensitive_fields(details)
    }

    if has_request_context():
        extras['ip_address'] = request.remote_addr
        extras['user_agent'] = request.headers.get('User-Agent', '')[:500]

    if current_user and getattr(current_user, 'is_authenticated', False):
        extras['user_id'] = current_user.get_id()

    log_level = getattr(logging, severity.upper(), logging.INFO)
    audit_logger.log(log_level, event_type, extra=extras)

"""Shared request-scoped SQLite connection handling.

Lives at the repo root (rather than inside ``app.py``) so blueprints can import
it without a circular import back to the application module.

Routes should use :func:`get_db`; the connection is cached on Flask's ``g`` for
the life of the request and closed by :func:`close_db`, which ``init_app``
registers as a teardown handler.  Do **not** call ``.close()`` on the returned
connection yourself.

The ``services/`` layer manages its own connections/transactions and is
deliberately left alone.
"""

import sqlite3

from flask import current_app, g

__all__ = ['get_db', 'close_db', 'init_app', 'get_db_connection']


def get_db():
    """Return the request-scoped SQLite connection, opening it if needed."""
    if 'db' not in g:
        conn = sqlite3.connect(current_app.config['DATABASE_PATH'])
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


def close_db(exception=None):
    """Close the request-scoped connection, if one was opened."""
    conn = g.pop('db', None)
    if conn is not None:
        conn.close()


def get_db_connection():
    """Backwards-compatible alias for :func:`get_db`.

    Older call sites expect this name.  Note that unlike the previous
    implementation the returned connection is shared and must not be closed by
    the caller -- teardown handles it.
    """
    return get_db()


def init_app(app):
    """Register the teardown handler on the given Flask app."""
    app.teardown_appcontext(close_db)

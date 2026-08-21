"""Shared fixtures for the route smoke-test suite.

Builds a throwaway sqlite database (never posa_wiki.db) under pytest's
tmp_path, applies the tracked migrations, seeds a handful of rows, builds
the FTS index, and points a freshly (re)imported ``app`` module at it.
"""

import importlib
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Tracked migrations, applied in order. NOTE: production's posa_wiki.db also
# has a `trips.series_type` column that was added by the ad-hoc
# `separate_series_trips.py` script rather than a tracked migration -- see
# the extra ALTER TABLE below and the discovery note in the test module.
MIGRATION_FILES = [
    "003_create_users_table.sql",
    "005_add_soft_delete.sql",
    "006_add_image_fields.sql",
    "007_create_audit_logs.sql",
    "008_add_duration_seconds.sql",
    "010_create_transcripts.sql",
]


def _run_create_database(scratch_dir: Path) -> Path:
    """Run create_database.py's schema/seed logic against a scratch dir.

    create_database.create_database() hardcodes a relative 'posa_wiki.db'
    connection string, so we chdir into an empty scratch directory, let it
    create the file there, then chdir back immediately.
    """
    import create_database

    cwd = os.getcwd()
    os.chdir(scratch_dir)
    try:
        create_database.create_database()
    finally:
        os.chdir(cwd)
    return scratch_dir / "posa_wiki.db"


def _apply_migrations(conn: sqlite3.Connection) -> None:
    for filename in MIGRATION_FILES:
        sql_path = REPO_ROOT / "migrations" / filename
        conn.executescript(sql_path.read_text())

    # Not a tracked migration, but app.py's /series and /trips routes
    # require this column (see discovery note in test_routes.py).
    conn.execute(
        "ALTER TABLE trips ADD COLUMN series_type VARCHAR DEFAULT 'trip'"
    )
    conn.commit()


def _seed_rows(conn: sqlite3.Connection) -> dict:
    """Insert minimal seed data and return the ids/values tests rely on."""
    videos = [
        {
            "video_id": "vid_short",
            "title": "Quiet Canoe Morning",
            "upload_date": "2024-01-05",
            "duration": "0:21",
            "duration_seconds": 21,
            "view_count": 100,
            "description": "A short paddle clip on a calm lake.",
            "youtube_tags": None,
        },
        {
            "video_id": "vid_medium",
            "title": "Boundary Waters Canoe Trip",
            "upload_date": "2024-06-10",
            "duration": "1:00:00",
            "duration_seconds": 3600,
            "view_count": 500,
            "description": "A canoe trip through the boundary waters.",
            "youtube_tags": json.dumps(["camping", "canoe", "dogs"]),
        },
        {
            "video_id": "vid_long",
            "title": "Ten Hour Winter Trek",
            "upload_date": "2023-03-01",
            "duration": "10:00:00",
            "duration_seconds": 36000,
            "view_count": 50,
            "description": "A marathon winter hike with the dogs.",
            "youtube_tags": None,
        },
    ]

    for v in videos:
        conn.execute(
            """
            INSERT INTO videos
                (video_id, title, upload_date, duration, duration_seconds,
                 view_count, description, youtube_tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                v["video_id"],
                v["title"],
                v["upload_date"],
                v["duration"],
                v["duration_seconds"],
                v["view_count"],
                v["description"],
                v["youtube_tags"],
            ),
        )

    # create_database.create_database() already seeded people 1-4 and dogs
    # 1-3 (Matthew Posa / Monty among them) -- reuse those rather than
    # duplicating rows, satisfying the "2 people, 2 dogs" minimum.
    person_id = 1  # Matthew Posa
    second_person_id = 2  # Funk
    dog_id = 1  # Monty
    second_dog_id = 2  # Rueger

    for video_id in ("vid_short", "vid_medium", "vid_long"):
        conn.execute(
            "INSERT INTO video_people (video_id, person_id, role) VALUES (?, ?, ?)",
            (video_id, person_id, "creator"),
        )
        conn.execute(
            "INSERT INTO video_dogs (video_id, dog_id, role) VALUES (?, ?, ?)",
            (video_id, dog_id, "companion"),
        )
    conn.execute(
        "INSERT INTO video_people (video_id, person_id, role) VALUES (?, ?, ?)",
        ("vid_medium", second_person_id, "guest"),
    )
    conn.execute(
        "INSERT INTO video_dogs (video_id, dog_id, role) VALUES (?, ?, ?)",
        ("vid_medium", second_dog_id, "companion"),
    )

    trip_id = 1
    conn.execute(
        """
        INSERT INTO trips (trip_id, trip_name, start_date, end_date, description, series_type)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (trip_id, "Boundary Waters Trip", "2024-06-10", "2024-06-12",
         "A multi-day canoe trip.", "trip"),
    )
    conn.execute(
        """
        INSERT INTO video_versions
            (version_id, trip_id, version_type, part_number, total_parts, video_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (1, trip_id, "main", 1, 1, "vid_medium"),
    )

    # An episodic series so /watch can prove Previous/Next episode links.
    # The name is deliberately outside seed_series.py's canonical list so
    # seeding/retiring in test_series.py stays idempotent; notes follow the
    # 'auto:' provenance convention assign_series.py writes.
    episodic_series_id = 900
    conn.execute(
        """
        INSERT INTO series (series_id, name, description, is_episodic, series_type)
        VALUES (?, ?, ?, ?, ?)
        """,
        (episodic_series_id, "Nightly Test Episodes",
         "Three seeded episodes used by the watch-page tests.", 1, "activity"),
    )
    for episode_number, video_id in enumerate(
            ("vid_short", "vid_medium", "vid_long"), start=1):
        conn.execute(
            """
            INSERT INTO video_series (video_id, series_id, episode_number, notes)
            VALUES (?, ?, ?, ?)
            """,
            (video_id, episodic_series_id, episode_number,
             "auto:conftest-episodic-seed"),
        )

    conn.commit()

    return {
        "episodic_series_id": episodic_series_id,
        "episodic_middle_video_id": "vid_medium",
        "episodic_prev_video_id": "vid_short",
        "episodic_next_video_id": "vid_long",
        "video_ids_desc_by_duration": ["vid_long", "vid_medium", "vid_short"],
        "video_ids_asc_by_duration": ["vid_short", "vid_medium", "vid_long"],
        "video_id": "vid_medium",
        "search_term": "Boundary",
        "person_id": person_id,
        "dog_id": dog_id,
        "trip_id": trip_id,
    }


@pytest.fixture(scope="session")
def seeded_db(tmp_path_factory):
    """Build the throwaway database once per test session."""
    scratch_dir = tmp_path_factory.mktemp("posa_wiki_test_db")
    db_path = _run_create_database(scratch_dir)

    conn = sqlite3.connect(db_path)
    try:
        _apply_migrations(conn)
        seed_info = _seed_rows(conn)
    finally:
        conn.close()

    import build_fts_index

    build_fts_index.build_fts_index(str(db_path))

    seed_info["path"] = str(db_path)
    return seed_info


@pytest.fixture(scope="session")
def app(seeded_db):
    """Import (or reimport) the real Flask app pointed at the seeded db.

    app.py reads DATABASE_PATH from config at *import* time, so the env vars
    must be set before the module (re)executes. Reload rather than a plain
    import so this works whether or not another test module already imported
    ``app``/``config`` against the real posa_wiki.db earlier in the session.
    """
    os.environ["DATABASE_PATH"] = seeded_db["path"]
    os.environ["POSA_WIKI_ENV"] = "testing"

    if "config" in sys.modules:
        importlib.reload(sys.modules["config"])

    if "app" in sys.modules:
        app_module = importlib.reload(sys.modules["app"])
    else:
        app_module = importlib.import_module("app")

    assert app_module.app.config["DATABASE_PATH"] == seeded_db["path"]

    return app_module.app


@pytest.fixture()
def client(app):
    return app.test_client()

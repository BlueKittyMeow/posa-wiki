"""Route smoke tests + duration unit tests.

The app fixture (tests/conftest.py) builds a throwaway sqlite database with
a handful of seeded videos/people/dogs/trip and points the real Flask app at
it, so these are real end-to-end route checks -- never against posa_wiki.db.
"""

import pytest

from utils.duration import format_seconds, parse_duration_to_seconds

# A string that's only ever emitted by the themed 404 page
# (templates/errors/404.html), used to prove the themed page rendered
# rather than some generic Flask/werkzeug 404.
NOT_FOUND_MARKER = b"Lost in the Wilderness"


# ---------------------------------------------------------------------------
# Simple 200 smoke tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/videos",
        "/people",
        "/dogs",
        "/series",
        "/trips",
        "/auth/login",
    ],
)
def test_static_routes_return_200(client, path):
    response = client.get(path)
    assert response.status_code == 200


def test_search_returns_200(client, seeded_db):
    response = client.get(f"/search?q={seeded_db['search_term']}")
    assert response.status_code == 200
    assert b"Boundary Waters Canoe Trip" in response.data


def test_search_empty_query_returns_200(client):
    response = client.get("/search?q=")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Detail pages (200 for seeded rows)
# ---------------------------------------------------------------------------

def test_video_detail_returns_200(client, seeded_db):
    response = client.get(f"/video/{seeded_db['video_id']}")
    assert response.status_code == 200


def test_person_detail_returns_200(client, seeded_db):
    response = client.get(f"/person/{seeded_db['person_id']}")
    assert response.status_code == 200


def test_dog_detail_returns_200(client, seeded_db):
    response = client.get(f"/dog/{seeded_db['dog_id']}")
    assert response.status_code == 200


def test_trip_detail_returns_200(client, seeded_db):
    response = client.get(f"/trip/{seeded_db['trip_id']}")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# 404s -- themed page, not a generic werkzeug 404
# ---------------------------------------------------------------------------

def test_video_detail_404_themed(client):
    response = client.get("/video/nonexistent-video-id")
    assert response.status_code == 404
    assert NOT_FOUND_MARKER in response.data


def test_person_detail_404_themed(client):
    response = client.get("/person/99999")
    assert response.status_code == 404
    assert NOT_FOUND_MARKER in response.data


def test_dog_detail_404_themed(client):
    response = client.get("/dog/99999")
    assert response.status_code == 404
    assert NOT_FOUND_MARKER in response.data


def test_trip_detail_404_themed(client):
    response = client.get("/trip/99999")
    assert response.status_code == 404
    assert NOT_FOUND_MARKER in response.data


# ---------------------------------------------------------------------------
# Sorting -- true numeric order, not lexicographic string order
# ---------------------------------------------------------------------------

def _positions_of(video_ids, html_bytes):
    """Return the position (index) each /video/<id> link appears at."""
    html = html_bytes.decode("utf-8")
    positions = []
    for video_id in video_ids:
        idx = html.find(f"/video/{video_id}")
        assert idx != -1, f"/video/{video_id} link not found in response"
        positions.append(idx)
    return positions


def test_videos_default_sort_is_upload_date(client, seeded_db):
    # Default sort is upload_date desc: 2024-06-10, 2024-01-05, 2023-03-01
    response = client.get("/videos")
    assert response.status_code == 200
    expected_order = ["vid_medium", "vid_short", "vid_long"]
    positions = _positions_of(expected_order, response.data)
    assert positions == sorted(positions)


def test_videos_sort_by_duration_is_numeric_desc(client, seeded_db):
    """duration_seconds 21 / 3600 / 36000 -- lexicographic sort on the
    display string ('0:21' vs '1:00:00' vs '10:00:00') would order these
    wrong; this asserts the real numeric order is used instead."""
    response = client.get("/videos?sort=duration")
    assert response.status_code == 200
    positions = _positions_of(seeded_db["video_ids_desc_by_duration"], response.data)
    assert positions == sorted(positions), (
        "expected duration sort (desc) to be numeric: "
        f"{seeded_db['video_ids_desc_by_duration']}"
    )


def test_videos_sort_by_duration_asc(client, seeded_db):
    response = client.get("/videos?sort=duration&order=asc")
    assert response.status_code == 200
    positions = _positions_of(seeded_db["video_ids_asc_by_duration"], response.data)
    assert positions == sorted(positions), (
        "expected duration sort (asc) to be numeric: "
        f"{seeded_db['video_ids_asc_by_duration']}"
    )


# ---------------------------------------------------------------------------
# utils/duration.py unit tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value,expected_seconds",
    [
        ("0:21", 21),
        ("9:31", 571),
        ("10:00:36", 36036),
        ("PT1H2M3S", 3723),
    ],
)
def test_parse_duration_to_seconds(value, expected_seconds):
    assert parse_duration_to_seconds(value) == expected_seconds


def test_parse_duration_to_seconds_unparseable_returns_none():
    assert parse_duration_to_seconds("not-a-duration") is None


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (21, "0:21"),
        (36036, "10:00:36"),
    ],
)
def test_format_seconds(seconds, expected):
    assert format_seconds(seconds) == expected


def test_format_seconds_none_is_graceful():
    # Must not raise; formatting an absent duration should degrade cleanly.
    assert format_seconds(None) is None

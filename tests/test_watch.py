"""The /watch/<video_id> night-friendly viewing page.

Runs against the throwaway seeded database from tests/conftest.py, never
posa_wiki.db.
"""

# Only ever emitted by templates/errors/404.html.
NOT_FOUND_MARKER = b"Lost in the Wilderness"


def test_watch_returns_200(client, seeded_db):
    response = client.get(f"/watch/{seeded_db['video_id']}")
    assert response.status_code == 200
    assert b"Boundary Waters Canoe Trip" in response.data


def test_watch_renders_player_container_and_video_id(client, seeded_db):
    body = client.get(f"/watch/{seeded_db['video_id']}").data.decode()

    # The id is handed to JS via a data attribute, never string-concatenated
    # into a <script> block.
    assert f'data-video-id="{seeded_db["video_id"]}"' in body
    assert 'id="watch-player"' in body
    assert "https://www.youtube.com/iframe_api" in body
    assert "js/watch.js" in body


def test_watch_renders_dim_controls(client, seeded_db):
    body = client.get(f"/watch/{seeded_db['video_id']}").data.decode()

    assert 'id="watch-overlay"' in body
    for level in ("0", "0.5", "0.75", "1"):
        assert f'data-dim="{level}"' in body
    assert 'id="watch-night-btn"' in body


def test_watch_shows_context(client, seeded_db):
    body = client.get(f"/watch/{seeded_db['video_id']}").data.decode()

    assert "2024-06-10" in body            # upload date
    assert "Matthew Posa" in body          # person chip
    assert "Monty" in body                 # dog chip
    assert "Nightly Test Episodes" in body  # series membership link


def test_watch_unknown_video_returns_themed_404(client):
    response = client.get("/watch/definitely-not-a-real-video-id")
    assert response.status_code == 404
    assert NOT_FOUND_MARKER in response.data


def test_watch_episodic_shows_prev_and_next(client, seeded_db):
    body = client.get(
        f"/watch/{seeded_db['episodic_middle_video_id']}").data.decode()

    assert f'/watch/{seeded_db["episodic_prev_video_id"]}"' in body
    assert f'/watch/{seeded_db["episodic_next_video_id"]}"' in body
    assert "Previous" in body
    assert "Next" in body


def test_watch_first_episode_has_next_but_no_previous(client, seeded_db):
    body = client.get(
        f"/watch/{seeded_db['episodic_prev_video_id']}").data.decode()

    assert f'/watch/{seeded_db["episodic_middle_video_id"]}"' in body
    assert f'/watch/{seeded_db["episodic_prev_video_id"]}"' not in body


def test_video_detail_links_to_watch_page(client, seeded_db):
    response = client.get(f"/video/{seeded_db['video_id']}")
    assert response.status_code == 200
    assert f'/watch/{seeded_db["video_id"]}"'.encode() in response.data
    assert "▶ Watch".encode() in response.data

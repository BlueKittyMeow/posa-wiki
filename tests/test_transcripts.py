"""Transcript ingestion: VTT parsing, archive ingest, and search integration.

The fixtures under ``tests/fixtures/`` are real yt-dlp subtitle sidecars from
the channel archive, trimmed to the first ~40 spoken phrases.  They keep the
awkward bits of YouTube's rolling ASR format (carried-over lines, per-word
``<00:00:01.599><c>`` timing tags, 10ms "settled" cues) so the parser is
exercised against the real thing rather than a tidy synthetic file.
"""

import importlib.util
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures"


def _load_ingest_module():
    """Import scripts/ingest_transcripts.py by path (scripts/ isn't a package)."""
    if "ingest_transcripts" in sys.modules:
        return sys.modules["ingest_transcripts"]
    spec = importlib.util.spec_from_file_location(
        "ingest_transcripts", REPO_ROOT / "scripts" / "ingest_transcripts.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["ingest_transcripts"] = module
    spec.loader.exec_module(module)
    return module


ingest_transcripts = _load_ingest_module()
parse_vtt = ingest_transcripts.parse_vtt


FIXTURE_FILES = sorted(FIXTURE_DIR.glob("*.en.vtt"))

# (fixture filename fragment, video id, a phrase that appears exactly once)
KNOWN_PHRASES = [
    ("Crap-Pie", "-zr_N8CDKUA", "It's the unsuccessful fishing show. So,"),
    ("Gear Load-Out", "B1azGQOz104", "Well, hello, ladies and gentlemen. I'm"),
]


def _fixture(fragment):
    for path in FIXTURE_FILES:
        if fragment in path.name:
            return path
    raise AssertionError(f"no fixture matching {fragment!r} in {FIXTURE_DIR}")


# --------------------------------------------------------------------------
# parse_vtt
# --------------------------------------------------------------------------

def test_fixtures_exist():
    assert FIXTURE_FILES, "expected trimmed .en.vtt fixtures in tests/fixtures/"


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.name[:30])
def test_parse_vtt_shape(path):
    segments = parse_vtt(path.read_text(encoding="utf-8"))

    assert segments, f"{path.name} produced no segments"
    for start, duration, text in segments:
        assert isinstance(start, float)
        assert start >= 0
        assert duration is None or duration >= 0
        assert text == text.strip()
        assert text


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.name[:30])
def test_parse_vtt_start_times_ascend(path):
    starts = [s for s, _d, _t in parse_vtt(path.read_text(encoding="utf-8"))]
    assert starts == sorted(starts)


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.name[:30])
def test_parse_vtt_collapses_rolling_repeats(path):
    """The staircase of repeated lines must be gone."""
    texts = [t for _s, _d, t in parse_vtt(path.read_text(encoding="utf-8"))]
    consecutive_dupes = [
        a for a, b in zip(texts, texts[1:]) if a == b
    ]
    assert not consecutive_dupes, f"duplicate consecutive segments: {consecutive_dupes[:3]}"


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.name[:30])
def test_parse_vtt_strips_markup(path):
    texts = [t for _s, _d, t in parse_vtt(path.read_text(encoding="utf-8"))]
    joined = "\n".join(texts)
    assert "<c>" not in joined
    assert "</c>" not in joined
    assert "&nbsp;" not in joined
    assert "align:start" not in joined
    # no leftover inline timestamp tags
    assert "<00:" not in joined


@pytest.mark.parametrize("fragment,_video_id,phrase", KNOWN_PHRASES,
                         ids=[k[0] for k in KNOWN_PHRASES])
def test_known_phrase_appears_exactly_once(fragment, _video_id, phrase):
    texts = [t for _s, _d, t in parse_vtt(_fixture(fragment).read_text(encoding="utf-8"))]
    assert texts.count(phrase) == 1, (
        f"{phrase!r} appeared {texts.count(phrase)} times"
    )


def test_parse_vtt_handles_plain_srt_style_vtt():
    """A hand-written, non-rolling VTT still parses sensibly."""
    text = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:03.000\n"
        "The first thing said.\n\n"
        "00:00:03.000 --> 00:00:05.500\n"
        "[Music]\n\n"
        "00:00:05.500 --> 00:00:07.000\n"
        "The second thing said.\n"
    )
    segments = parse_vtt(text)
    assert [t for _s, _d, t in segments] == [
        "The first thing said.",
        "The second thing said.",
    ]
    assert segments[0][0] == 1.0


def test_parse_vtt_empty_input():
    assert parse_vtt("WEBVTT\n\n") == []


def test_extract_video_id():
    extract = ingest_transcripts.extract_video_id
    assert extract("Crap-Pie [Episode 15] [-zr_N8CDKUA].en.vtt") == "-zr_N8CDKUA"
    assert extract("Gear Load-Out [B1azGQOz104].en-orig.vtt") == "B1azGQOz104"
    assert extract("no brackets here.en.vtt") is None


# --------------------------------------------------------------------------
# ingest against a temp database + temp archive
# --------------------------------------------------------------------------

@pytest.fixture()
def temp_archive(tmp_path):
    """An archive tree shaped like /mnt/media6t/archive/posa/<dir>/<file>."""
    archive = tmp_path / "archive" / "posa"
    for path in FIXTURE_FILES:
        video_dir = archive / path.name.rsplit(" [", 1)[0]
        video_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, video_dir / path.name)
    return archive


@pytest.fixture()
def transcript_db(tmp_path):
    """A minimal database with the videos rows the fixtures refer to."""
    db_path = tmp_path / "transcripts.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE videos (video_id VARCHAR PRIMARY KEY, title VARCHAR)"
    )
    for path in FIXTURE_FILES:
        video_id = ingest_transcripts.extract_video_id(path.name)
        conn.execute(
            "INSERT INTO videos (video_id, title) VALUES (?, ?)",
            (video_id, path.name.rsplit(" [", 1)[0]),
        )
    conn.commit()
    return conn


def test_ingest_creates_schema_and_rows(transcript_db, temp_archive):
    summary = ingest_transcripts.ingest(transcript_db, str(temp_archive), quiet=True)

    assert summary["ingested"] == len(FIXTURE_FILES)
    assert summary["unknown_video"] == 0
    assert summary["errors"] == 0
    assert summary["segments"] > 0

    assert ingest_transcripts.tables_present(transcript_db)

    seg_count = transcript_db.execute(
        "SELECT COUNT(*) FROM transcript_segments"
    ).fetchone()[0]
    assert seg_count == summary["segments"]

    status_rows = transcript_db.execute(
        "SELECT video_id, status, source, language, segment_count FROM transcript_status"
    ).fetchall()
    assert len(status_rows) == len(FIXTURE_FILES)
    for _vid, status, source, language, count in status_rows:
        assert status == "ingested"
        assert source == "youtube-asr-vtt"
        assert language == "en"
        assert count > 0

    # FTS mirror was populated by the migration's triggers
    fts_count = transcript_db.execute(
        "SELECT COUNT(*) FROM transcripts_fts"
    ).fetchone()[0]
    assert fts_count == seg_count

    hits = transcript_db.execute(
        "SELECT COUNT(*) FROM transcripts_fts WHERE transcripts_fts MATCH ?",
        ('"unsuccessful fishing show"',),
    ).fetchone()[0]
    assert hits >= 1


def test_ingest_is_idempotent(transcript_db, temp_archive):
    first = ingest_transcripts.ingest(transcript_db, str(temp_archive), quiet=True)
    second = ingest_transcripts.ingest(transcript_db, str(temp_archive), quiet=True)

    assert second["ingested"] == 0
    assert second["segments"] == 0
    assert second["skipped"] == len(FIXTURE_FILES)

    total = transcript_db.execute(
        "SELECT COUNT(*) FROM transcript_segments"
    ).fetchone()[0]
    assert total == first["segments"]


def test_ingest_redo_replaces_one_video(transcript_db, temp_archive):
    ingest_transcripts.ingest(transcript_db, str(temp_archive), quiet=True)
    video_id = "-zr_N8CDKUA"
    before = transcript_db.execute(
        "SELECT COUNT(*) FROM transcript_segments WHERE video_id = ?", (video_id,)
    ).fetchone()[0]
    assert before > 0

    summary = ingest_transcripts.ingest(
        transcript_db, str(temp_archive), redo=video_id, quiet=True
    )
    assert summary["ingested"] == 1

    after = transcript_db.execute(
        "SELECT COUNT(*) FROM transcript_segments WHERE video_id = ?", (video_id,)
    ).fetchone()[0]
    assert after == before

    total_status = transcript_db.execute(
        "SELECT COUNT(*) FROM transcript_status WHERE video_id = ?", (video_id,)
    ).fetchone()[0]
    assert total_status == 1


def test_ingest_dry_run_writes_nothing(transcript_db, temp_archive):
    summary = ingest_transcripts.ingest(
        transcript_db, str(temp_archive), dry_run=True, quiet=True
    )
    assert summary["ingested"] == len(FIXTURE_FILES)
    assert transcript_db.execute(
        "SELECT COUNT(*) FROM transcript_segments"
    ).fetchone()[0] == 0


def test_ingest_skips_unknown_video_ids(tmp_path, temp_archive):
    """A sidecar for a video not yet in `videos` is reported, never fatal."""
    conn = sqlite3.connect(tmp_path / "empty.db")
    conn.execute("CREATE TABLE videos (video_id VARCHAR PRIMARY KEY, title VARCHAR)")
    conn.commit()

    summary = ingest_transcripts.ingest(conn, str(temp_archive), quiet=True)

    assert summary["ingested"] == 0
    assert summary["unknown_video"] == len(FIXTURE_FILES)
    assert conn.execute("SELECT COUNT(*) FROM transcript_segments").fetchone()[0] == 0


def test_prefers_en_over_en_orig(tmp_path):
    archive = tmp_path / "posa"
    archive.mkdir()
    (archive / "A Video [abcdef].en.vtt").write_text("WEBVTT\n")
    (archive / "A Video [abcdef].en-orig.vtt").write_text("WEBVTT\n")

    found = ingest_transcripts.discover_subtitles(str(archive))
    assert list(found) == ["abcdef"]
    assert found["abcdef"].endswith(".en.vtt")


# --------------------------------------------------------------------------
# /search integration
# --------------------------------------------------------------------------

TRANSCRIPT_PHRASE = "the portage trail was absolutely swarming with mosquitoes"


@pytest.fixture()
def seeded_transcript(seeded_db):
    """Put one known transcript segment on vid_medium in the shared test db."""
    conn = sqlite3.connect(seeded_db["path"])
    try:
        conn.execute(
            "DELETE FROM transcript_segments WHERE video_id = ?", ("vid_medium",)
        )
        conn.execute(
            "DELETE FROM transcript_status WHERE video_id = ?", ("vid_medium",)
        )
        conn.execute(
            """
            INSERT INTO transcript_segments
                (video_id, start_seconds, duration_seconds, text)
            VALUES (?, ?, ?, ?)
            """,
            ("vid_medium", 754.0, 2.5, TRANSCRIPT_PHRASE),
        )
        conn.execute(
            """
            INSERT INTO transcript_status
                (video_id, status, source, language, segment_count, ingested_at)
            VALUES (?, 'ingested', 'youtube-asr-vtt', 'en', 1, '2026-08-20T00:00:00')
            """,
            ("vid_medium",),
        )
        conn.commit()
    finally:
        conn.close()
    return {"video_id": "vid_medium", "start": 754}


def test_search_returns_transcript_hit(client, seeded_transcript):
    response = client.get("/search?q=swarming+with+mosquitoes")
    assert response.status_code == 200

    body = response.get_data(as_text=True)
    assert "Spoken in videos" in body
    assert "mosquitoes" in body
    assert (
        "https://www.youtube.com/watch?v=vid_medium&amp;t=754s" in body
        or "https://www.youtube.com/watch?v=vid_medium&t=754s" in body
    )
    assert "12:34" in body  # 754 seconds, human timestamp
    assert 'target="_blank"' in body


def test_search_without_transcript_hits_omits_section(client, seeded_transcript):
    response = client.get("/search?q=Boundary")
    assert response.status_code == 200
    assert "Spoken in videos" not in response.get_data(as_text=True)


def test_search_transcript_query_is_escaped(client, seeded_transcript):
    """A query full of FTS operators must not blow up the route."""
    response = client.get('/search?q=mosquitoes"+OR+NEAR(x)')
    assert response.status_code == 200

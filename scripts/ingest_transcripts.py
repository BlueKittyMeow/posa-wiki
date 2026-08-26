#!/usr/bin/env python3
"""Ingest transcripts from the local yt-dlp subtitle sidecars into the wiki DB.

Source of truth is the channel archive built by ``scripts/archive_channel.sh``.
Each archived video has a WebVTT sidecar next to the media file::

    /mnt/media6t/archive/posa/<dirname>/<title> [<video_id>].en.vtt

The video id is always the last ``[...]`` group in the filename.

The script is idempotent: a video already present in ``transcript_status`` is
skipped, so re-running after a fresh archive pass only picks up new material.
Use ``--redo VIDEO_ID`` to force one video to be re-parsed.

    ./venv/bin/python scripts/ingest_transcripts.py --dry-run
    ./venv/bin/python scripts/ingest_transcripts.py
    ./venv/bin/python scripts/ingest_transcripts.py --redo 58zxwCbnXpA

Parsing notes
-------------
YouTube's auto-generated (ASR) VTT is a *rolling caption* format, not a list of
discrete phrases.  A typical stretch looks like::

    00:13:11.760 --> 00:13:14.069 align:start position:0%
    It's really low in the water. Whatever
    it<00:13:11.839><c> is.</c><00:13:12.240><c> Where</c><00:13:12.320><c> is</c><00:13:12.480><c> it?</c>

    00:13:14.069 --> 00:13:14.079 align:start position:0%
    it is. Where is it? It's right there.

i.e. every cue repeats the previously displayed line(s) and adds one new line
carrying per-word timing tags, and 10ms "settled" cues restate the finished
line.  Naively storing cue text produces a staircase of duplicates.  The parser
therefore strips the inline markup, then emits a line only the first time it is
seen within a short rolling window, keeping its earliest start time.
"""

import argparse
import html
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARCHIVE_DIR = "/mnt/media6t/archive/posa"
DEFAULT_DB = str(REPO_ROOT / "posa_wiki.db")
MIGRATION_PATH = REPO_ROOT / "migrations" / "010_create_transcripts.sql"

SOURCE_YOUTUBE_ASR = "youtube-asr-vtt"

# Video id is the last bracketed group in the filename, e.g.
# "Gear Load-Out For An 8 Night Wilderness Adventure [B1azGQOz104].en.vtt".
# Real YouTube ids are 11 chars; the pattern stays loose so test fixtures and
# any hand-named file still resolve.
VIDEO_ID_RE = re.compile(r"\[([A-Za-z0-9_-]{3,})\]")

TIMING_RE = re.compile(
    r"(?P<start>\d{1,3}:\d{2}:\d{2}[.,]\d{3}|\d{1,3}:\d{2}[.,]\d{3})"
    r"\s*-->\s*"
    r"(?P<end>\d{1,3}:\d{2}:\d{2}[.,]\d{3}|\d{1,3}:\d{2}[.,]\d{3})"
)

# <00:00:01.599>, <c>, <c.colorE5E5E5>, </c>, <v Speaker>, </v>, <b>, <i> ...
MARKUP_RE = re.compile(r"</?[a-zA-Z][^>]*>|<\d{1,3}:\d{2}:\d{2}[.,]\d{3}>")

# Lines that carry no speech: musical notes, [Music]/[Applause] bracket tags,
# bare dashes/chevrons, and stray numeric cue identifiers.
NOISE_ONLY_RE = re.compile(
    r"^(?:[\s♪♫♩♬>\-_.]|\[[^\]]*\]|\d)+$"
)

# How many recently emitted lines to compare against when de-duplicating the
# rolling repeats.  YouTube shows at most two lines at a time; three gives a
# little slack without swallowing a phrase genuinely repeated minutes later.
DEDUPE_WINDOW = 3


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------

def parse_timestamp(value):
    """Return seconds (float) for an ``HH:MM:SS.mmm`` or ``MM:SS.mmm`` stamp."""
    value = value.strip().replace(",", ".")
    parts = value.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours, minutes, seconds = "0", parts[0], parts[1]
    else:
        raise ValueError(f"unrecognised VTT timestamp: {value!r}")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def clean_line(line):
    """Strip inline VTT markup/entities and normalise whitespace."""
    line = MARKUP_RE.sub("", line)
    line = html.unescape(line)
    line = line.replace(" ", " ")
    line = re.sub(r"\s+", " ", line).strip()
    # ">>" is a speaker-change marker, not speech.
    return re.sub(r"^>>+\s*", "", line)


def _iter_cues(text):
    """Yield ``(start_seconds, end_seconds, [raw_line, ...])`` per VTT cue.

    Driven off the timing lines rather than blank-line-separated blocks:
    yt-dlp writes cue bodies containing a line holding a single space, so
    splitting on ``\\n\\s*\\n`` tears real cues in half.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cue = None
    for raw in lines:
        match = TIMING_RE.search(raw) if "-->" in raw else None
        if match:
            if cue is not None:
                yield cue
            try:
                cue = (
                    parse_timestamp(match.group("start")),
                    parse_timestamp(match.group("end")),
                    [],
                )
            except ValueError:
                cue = None
            continue
        if cue is not None:
            cue[2].append(raw)
    if cue is not None:
        yield cue


def parse_vtt(text):
    """Parse WebVTT (incl. YouTube rolling ASR captions) into segments.

    Returns a list of ``(start_seconds, duration_seconds, text)`` tuples in
    ascending start order, one entry per spoken phrase, with the inline
    word-timing markup stripped and the rolling repeats collapsed.
    """
    emitted = []          # [[start, end, text], ...]
    recent = []           # rolling window of the last DEDUPE_WINDOW texts

    for start, end, raw_lines in _iter_cues(text):
        for raw in raw_lines:
            line = clean_line(raw)
            if not line or NOISE_ONLY_RE.match(line):
                continue
            if line in recent:
                # A carried-over line from the previous cue: it is already
                # stored with its (earlier, correct) start time.  Extend that
                # segment's end so durations stay sensible.
                for entry in reversed(emitted):
                    if entry[2] == line:
                        entry[1] = max(entry[1], end)
                        break
                continue
            emitted.append([start, end, line])
            recent.append(line)
            if len(recent) > DEDUPE_WINDOW:
                recent.pop(0)

    segments = []
    for index, (start, end, line) in enumerate(emitted):
        # Prefer "up to the next phrase" for duration; it matches how the
        # caption actually reads on screen and never overlaps.
        if index + 1 < len(emitted):
            duration = emitted[index + 1][0] - start
        else:
            duration = end - start
        if duration <= 0:
            duration = max(end - start, 0.0)
        segments.append((round(start, 3), round(duration, 3), line))
    return segments


# --------------------------------------------------------------------------
# archive discovery
# --------------------------------------------------------------------------

def extract_video_id(filename):
    """Return the ``[video_id]`` from an archive filename, or None."""
    matches = VIDEO_ID_RE.findall(filename)
    return matches[-1] if matches else None


def discover_subtitles(archive_dir):
    """Map video_id -> best subtitle path under ``archive_dir``.

    ``.en.vtt`` wins over ``.en-orig.vtt`` when a video has both (the plain
    ``.en`` track is the one YouTube serves as the default caption).
    """
    found = {}
    for root, _dirs, files in os.walk(archive_dir):
        for name in sorted(files):
            if name.endswith(".en.vtt"):
                priority = 0
            elif name.endswith(".en-orig.vtt"):
                priority = 1
            else:
                continue
            video_id = extract_video_id(name)
            if not video_id:
                continue
            path = os.path.join(root, name)
            existing = found.get(video_id)
            if existing is None or priority < existing[0]:
                found[video_id] = (priority, path)
    return {vid: path for vid, (_priority, path) in sorted(found.items())}


# --------------------------------------------------------------------------
# database
# --------------------------------------------------------------------------

def tables_present(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
    ).fetchall()
    names = {row[0] for row in rows}
    return {"transcript_segments", "transcript_status", "transcripts_fts"} <= names


def ensure_schema(conn, quiet=False):
    """Apply migration 010 if the transcript tables are missing."""
    if tables_present(conn):
        return False
    if not quiet:
        print(f"- applying {MIGRATION_PATH.name}")
    conn.executescript(MIGRATION_PATH.read_text())
    conn.commit()
    return True


def known_video_ids(conn):
    return {row[0] for row in conn.execute("SELECT video_id FROM videos")}


def already_ingested(conn):
    return {row[0] for row in conn.execute("SELECT video_id FROM transcript_status")}


def clear_video(conn, video_id):
    """Remove a video's segments and status row (data, not files)."""
    conn.execute("DELETE FROM transcript_segments WHERE video_id = ?", (video_id,))
    conn.execute("DELETE FROM transcript_status WHERE video_id = ?", (video_id,))


def upsert_status(conn, video_id, status, source, language, segment_count, error=None):
    conn.execute(
        """
        INSERT INTO transcript_status
            (video_id, status, source, language, segment_count, ingested_at, error)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(video_id) DO UPDATE SET
            status = excluded.status,
            source = excluded.source,
            language = excluded.language,
            segment_count = excluded.segment_count,
            ingested_at = excluded.ingested_at,
            error = excluded.error
        """,
        (
            video_id,
            status,
            source,
            language,
            segment_count,
            datetime.now().isoformat(timespec="seconds"),
            error,
        ),
    )


def has_source_column(conn):
    """True once migration 013 has added transcript_segments.source."""
    return any(row[1] == "source"
               for row in conn.execute("PRAGMA table_info(transcript_segments)"))


def insert_segments(conn, video_id, segments, source=SOURCE_YOUTUBE_ASR):
    """Insert parsed segments, stamping the source when the column exists.

    Migration 013 added ``transcript_segments.source`` so Whisper rows can sit
    alongside these without /search returning both. This script kept writing
    NULL for a day after that migration landed -- harmless (the search
    preference treats NULL as "not Whisper") but it left 9 167 untagged rows,
    so the column is now filled in explicitly. Databases predating 013 still
    work: the column is simply omitted.
    """
    if has_source_column(conn):
        conn.executemany(
            """
            INSERT INTO transcript_segments
                (video_id, start_seconds, duration_seconds, text, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            [(video_id, start, duration, text, source)
             for start, duration, text in segments],
        )
        return
    conn.executemany(
        """
        INSERT INTO transcript_segments
            (video_id, start_seconds, duration_seconds, text)
        VALUES (?, ?, ?, ?)
        """,
        [(video_id, start, duration, text) for start, duration, text in segments],
    )


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def ingest(conn, archive_dir, redo=None, dry_run=False, quiet=False):
    """Run one ingest pass.  Returns a summary dict."""
    ensure_schema(conn, quiet=quiet)

    subtitles = discover_subtitles(archive_dir)
    if not quiet:
        print(f"- found {len(subtitles)} subtitle file(s) under {archive_dir}")

    videos = known_video_ids(conn)
    done = already_ingested(conn)

    summary = {
        "ingested": 0,
        "skipped": 0,
        "unknown_video": 0,
        "errors": 0,
        "segments": 0,
        "files": len(subtitles),
    }

    if redo:
        if redo not in subtitles:
            print(f"! --redo {redo}: no subtitle file for that id under {archive_dir}",
                  file=sys.stderr)
            return summary
        subtitles = {redo: subtitles[redo]}
        if not dry_run:
            clear_video(conn, redo)
        done.discard(redo)
        if not quiet:
            print(f"- --redo {redo}: cleared existing segments/status")

    for video_id, path in subtitles.items():
        if video_id in done:
            summary["skipped"] += 1
            continue
        if video_id not in videos:
            summary["unknown_video"] += 1
            print(
                f"! {video_id}: not in videos table -- skipping "
                f"({os.path.basename(path)}). Run scripts/update_catalog.py first.",
                file=sys.stderr,
            )
            continue

        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
            segments = parse_vtt(text)
        except Exception as exc:  # noqa: BLE001 - one bad file must not kill the run
            summary["errors"] += 1
            print(f"! {video_id}: parse failed: {exc}", file=sys.stderr)
            if not dry_run:
                upsert_status(conn, video_id, "error", SOURCE_YOUTUBE_ASR, "en",
                              0, error=str(exc))
            continue

        if not segments:
            summary["errors"] += 0
            if not quiet:
                print(f"- {video_id}: no usable cues -> no_captions")
            if not dry_run:
                upsert_status(conn, video_id, "no_captions", SOURCE_YOUTUBE_ASR,
                              "en", 0)
            continue

        summary["ingested"] += 1
        summary["segments"] += len(segments)
        if not quiet:
            print(f"- {video_id}: {len(segments)} segments  ({os.path.basename(path)})")
        if not dry_run:
            insert_segments(conn, video_id, segments)
            upsert_status(conn, video_id, "ingested", SOURCE_YOUTUBE_ASR, "en",
                          len(segments))

    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Ingest yt-dlp WebVTT subtitle sidecars into the wiki database.",
    )
    parser.add_argument("--archive-dir", default=DEFAULT_ARCHIVE_DIR,
                        help=f"archive root to scan (default: {DEFAULT_ARCHIVE_DIR})")
    parser.add_argument("--db", default=DEFAULT_DB,
                        help="SQLite database path (default: repo posa_wiki.db)")
    parser.add_argument("--redo", metavar="VIDEO_ID",
                        help="re-ingest a single video, replacing its segments")
    parser.add_argument("--dry-run", action="store_true",
                        help="parse and report, but write nothing")
    parser.add_argument("--quiet", action="store_true", help="less per-file chatter")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.archive_dir):
        print(f"Archive directory not found: {args.archive_dir}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db)
    try:
        summary = ingest(
            conn,
            args.archive_dir,
            redo=args.redo,
            dry_run=args.dry_run,
            quiet=args.quiet,
        )
    finally:
        conn.close()

    label = "DRY RUN -- nothing written" if args.dry_run else "done"
    print(
        f"\n{label}: {summary['ingested']} ingested, "
        f"{summary['skipped']} already present, "
        f"{summary['unknown_video']} unknown video id, "
        f"{summary['errors']} errors, "
        f"{summary['segments']} segments total "
        f"({summary['files']} subtitle files seen)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

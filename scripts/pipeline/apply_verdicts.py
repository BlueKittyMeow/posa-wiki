#!/usr/bin/env python3
"""Stage 3 — write Whisper transcripts and judge verdicts into the wiki DB.

Runs on Factotum, where the archive and the deployed database both live::

    cd /srv/posa-wiki
    ./venv/bin/python scripts/pipeline/apply_verdicts.py --dry-run
    ./venv/bin/python scripts/pipeline/apply_verdicts.py

What it writes, per video:

* the Whisper segments, as ``transcript_segments`` rows with
  ``source = 'whisper-large-v3'``.  **The YouTube ASR rows are never
  deleted** -- they stay as the second witness and as a fallback.  ``/search``
  simply *prefers* Whisper rows for a video that has them
  (``search_transcripts`` in ``app.py``).
* every applied ``correct`` verdict, as a minimal in-segment edit plus a row in
  ``transcript_corrections`` holding the pre-edit text and which model said so.
* every ``escalate`` verdict -- and every correction the applier *refused* --
  as an ``open`` row in ``transcript_review_queue`` for ``/admin/review/transcripts``.

ALL LLM output is candidate-only.  A refused correction is not a failure: it
becomes a question for Lara, which is exactly what the appellate tier is.

Idempotent: a video already carrying Whisper segments is skipped unless
``--redo`` is passed, and queue rows are keyed by a content hash so re-running
never duplicates something already decided.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pipeline.corrections import (  # noqa: E402
    apply_edits, group_edits, plan_correction)
from scripts.pipeline.sentences import sentences_from_segments  # noqa: E402

DEFAULT_ARCHIVE_DIR = "/mnt/media6t/archive/posa"
DEFAULT_DB = str(REPO_ROOT / "posa_wiki.db")
MIGRATION_PATH = REPO_ROOT / "migrations" / "013_transcript_review.sql"
BASE_MIGRATION_PATH = REPO_ROOT / "migrations" / "010_create_transcripts.sql"

SOURCE_WHISPER = "whisper-large-v3"
SOURCE_YOUTUBE_ASR = "youtube-asr-vtt"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------

def _columns(conn, table):
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.OperationalError:
        return set()


def ensure_schema(conn, quiet=False):
    """Apply migrations 010 and 013 as needed.  Safe to call repeatedly."""
    names = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
    if not {"transcript_segments", "transcript_status"} <= names:
        if not quiet:
            print(f"- applying {BASE_MIGRATION_PATH.name}")
        conn.executescript(BASE_MIGRATION_PATH.read_text())
        names = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
    if ("source" in _columns(conn, "transcript_segments")
            and "judge_status" in _columns(conn, "transcript_status")
            and "transcript_review_queue" in names):
        return False
    if not quiet:
        print(f"- applying {MIGRATION_PATH.name}")
    # The migration is written as a fresh apply; run it statement by statement
    # so a partially-applied schema (e.g. the ALTERs already done) still gets
    # the remaining objects.  Comment lines are stripped first -- a `--` line
    # sitting above a statement would otherwise ride along with it.
    body = "\n".join(line for line in MIGRATION_PATH.read_text().splitlines()
                     if not line.lstrip().startswith("--"))
    for statement in body.split(";"):
        statement = statement.strip()
        if not statement:
            continue
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" in str(exc):
                continue
            raise
    conn.commit()
    return True


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def item_id_for(video_id, start_seconds, draft_sentence, span):
    digest = hashlib.sha1(
        "|".join([video_id, f"{float(start_seconds or 0):.2f}",
                  draft_sentence or "", str(span or "")]).encode("utf-8")
    ).hexdigest()[:20]
    return f"{video_id}:{digest}"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def nonempty_segments(whisper):
    return [s for s in (whisper.get("segments") or [])
            if (s.get("text") or "").strip()]


def video_exists(conn, video_id) -> bool:
    return conn.execute("SELECT 1 FROM videos WHERE video_id = ?",
                        (video_id,)).fetchone() is not None


def has_whisper(conn, video_id) -> bool:
    return conn.execute(
        "SELECT 1 FROM transcript_segments WHERE video_id = ? AND source = ? "
        "LIMIT 1", (video_id, SOURCE_WHISPER)).fetchone() is not None


def clear_whisper(conn, video_id):
    """Remove only this video's Whisper rows (never the YouTube witnesses)."""
    conn.execute("DELETE FROM transcript_segments WHERE video_id = ? AND source = ?",
                 (video_id, SOURCE_WHISPER))


# --------------------------------------------------------------------------
# the work
# --------------------------------------------------------------------------

def plan_video(whisper: dict, verdicts: dict):
    """Compute the final segment texts, the correction log and the queue rows.

    Pure: no database, no files.  Returns
    ``(segments, texts, corrections, queue_items, stats)``.
    """
    segments = nonempty_segments(whisper)
    _draft, spans, sentences = sentences_from_segments(segments)
    by_index = {s.index: s for s in sentences}
    span_by_segment = {s.segment_index: s for s in spans}

    texts = [(s.get("text") or "").strip() for s in segments]
    corrections = []
    queue_items = []
    stats = {"applied": 0, "refused": 0, "escalated": 0, "confirmed": 0,
             "unmatched": 0}
    # Every plan is computed against the ORIGINAL draft, so a second ruling
    # touching a segment that has already been edited would splice at stale
    # offsets and shred the text.  One edit per segment per run; the loser
    # goes to the human with its proposal intact.
    edited_segments = set()

    for ruling in verdicts.get("rulings") or []:
        verdict = str(ruling.get("verdict", "")).lower()
        sentence = by_index.get(ruling.get("sentence_index"))
        if sentence is None or sentence.text != ruling.get("draft_sentence"):
            # The Whisper JSON and the verdicts must describe the same draft.
            sentence = next(
                (s for s in sentences if s.text == ruling.get("draft_sentence")),
                None)
        if sentence is None:
            stats["unmatched"] += 1
            continue

        if verdict == "confirm":
            stats["confirmed"] += 1
            continue

        queue_reason = None
        if verdict == "correct":
            plan = plan_correction(sentence.text, ruling.get("correction") or "",
                                   spans, sentence.start_char)
            grouped = group_edits(plan.edits)
            clash = sorted(set(grouped) & edited_segments)
            if plan.applicable and not clash:
                for segment_index, edits in grouped.items():
                    before = texts[segment_index]
                    after = apply_edits(before, edits)
                    if after == before:
                        continue
                    texts[segment_index] = after
                    edited_segments.add(segment_index)
                    corrections.append({
                        "segment_index": segment_index,
                        "start_seconds": span_by_segment[segment_index].start,
                        "before_text": before,
                        "after_text": after,
                        "span": ruling.get("span"),
                        "reasoning": ruling.get("reasoning"),
                    })
                stats["applied"] += 1
                continue
            stats["refused"] += 1
            if clash:
                queue_reason = (f"segment {clash[0]} was already corrected by an "
                                "earlier ruling in this run")
            else:
                queue_reason = ("; ".join(plan.refusals)
                                or "correction not applicable")

        # escalate, or a correction the applier refused
        stats["escalated"] += 1
        note = ruling.get("reasoning") or ""
        if queue_reason:
            note = (note + f" [applier: {queue_reason}]").strip()
        queue_items.append({
            "start_seconds": sentence.start,
            "end_seconds": sentence.end,
            "draft_sentence": sentence.text,
            "witness_disagreement": ruling.get("witness_disagreement") or "",
            "judge_reasoning": note,
            # Whatever reading the judge offered rides along, even on an
            # escalate: it is the starting point for the human, never a write.
            "proposed_correction": ruling.get("correction") or None,
            "span": ruling.get("span"),
        })

    return segments, texts, corrections, queue_items, stats


def apply_video(conn, video_id: str, whisper: dict, verdicts: dict,
                judge_provenance: str, quiet=False):
    segments, texts, corrections, queue_items, stats = plan_video(whisper, verdicts)

    clear_whisper(conn, video_id)
    segment_ids = []
    for seg, text in zip(segments, texts):
        start = float(seg.get("start") or 0.0)
        end = seg.get("end")
        duration = (float(end) - start) if end is not None else None
        cursor = conn.execute(
            "INSERT INTO transcript_segments "
            "(video_id, start_seconds, duration_seconds, text, source) "
            "VALUES (?, ?, ?, ?, ?)",
            (video_id, round(start, 3),
             round(duration, 3) if duration is not None else None,
             text, SOURCE_WHISPER))
        segment_ids.append(cursor.lastrowid)

    for correction in corrections:
        conn.execute(
            "INSERT INTO transcript_corrections "
            "(video_id, segment_id, start_seconds, before_text, after_text, "
            " span, reasoning, provenance, applied_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (video_id, segment_ids[correction["segment_index"]],
             correction["start_seconds"], correction["before_text"],
             correction["after_text"], correction["span"],
             correction["reasoning"], judge_provenance, now()))

    queued = 0
    for item in queue_items:
        item_id = item_id_for(video_id, item["start_seconds"],
                              item["draft_sentence"], item["span"])
        cursor = conn.execute(
            "INSERT OR IGNORE INTO transcript_review_queue "
            "(item_id, video_id, start_seconds, end_seconds, draft_sentence, "
            " witness_disagreement, judge_reasoning, proposed_correction, "
            " status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)",
            (item_id, video_id, round(item["start_seconds"], 2),
             round(item["end_seconds"], 2), item["draft_sentence"],
             item["witness_disagreement"], item["judge_reasoning"],
             item["proposed_correction"], now()))
        queued += cursor.rowcount or 0

    judge_status = ("judged" if not verdicts.get("stats", {}).get("parse_failures")
                    else "judged")
    conn.execute(
        "INSERT INTO transcript_status "
        "(video_id, status, source, language, segment_count, ingested_at, "
        " whisper_status, whisper_segment_count, whisper_ingested_at, "
        " judge_status, judged_at, corrections_applied, escalations_queued) "
        "VALUES (?, 'ingested', ?, 'en', ?, ?, 'ingested', ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(video_id) DO UPDATE SET "
        " whisper_status = excluded.whisper_status,"
        " whisper_segment_count = excluded.whisper_segment_count,"
        " whisper_ingested_at = excluded.whisper_ingested_at,"
        " judge_status = excluded.judge_status,"
        " judged_at = excluded.judged_at,"
        " corrections_applied = excluded.corrections_applied,"
        " escalations_queued = excluded.escalations_queued",
        (video_id, SOURCE_YOUTUBE_ASR, len(segments), now(),
         len(segments), now(), judge_status, now(),
         len(corrections), queued))

    stats = dict(stats)
    stats.update({"segments": len(segments), "corrections_logged": len(corrections),
                  "queued": queued})
    if not quiet:
        print(f"- {video_id}: {len(segments)} whisper segments, "
              f"{stats['applied']} corrections applied "
              f"({len(corrections)} segment edits), {queued} queued, "
              f"{stats['confirmed']} confirmed, {stats['refused']} refused")
    return stats


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def discover(archive_dir):
    whisper_dir = Path(archive_dir) / "transcripts_whisper"
    verdict_dir = Path(archive_dir) / "transcripts_verdicts"
    pairs = {}
    if not whisper_dir.is_dir():
        return pairs
    for path in sorted(whisper_dir.glob("*.whisper.json")):
        video_id = path.name[:-len(".whisper.json")]
        verdict_path = verdict_dir / f"{video_id}.verdicts.json"
        pairs[video_id] = (path, verdict_path if verdict_path.exists() else None)
    return pairs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--archive-dir", default=DEFAULT_ARCHIVE_DIR)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--only", action="append", default=[], metavar="VIDEO_ID")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--require-verdicts", action="store_true",
                        help="skip videos that have not been judged yet")
    parser.add_argument("--redo", action="store_true",
                        help="replace existing whisper segments for these videos")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    pairs = discover(args.archive_dir)
    if not pairs:
        print(f"No whisper transcripts under {args.archive_dir}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(args.db)
    try:
        ensure_schema(conn, quiet=args.quiet)

        todo = args.only or list(pairs)
        totals = {"videos": 0, "segments": 0, "applied": 0, "queued": 0,
                  "refused": 0, "confirmed": 0, "skipped": 0, "unmatched": 0}
        for video_id in todo:
            if video_id not in pairs:
                print(f"! {video_id}: no whisper transcript", file=sys.stderr)
                continue
            whisper_path, verdict_path = pairs[video_id]
            if args.require_verdicts and verdict_path is None:
                totals["skipped"] += 1
                continue
            if not video_exists(conn, video_id):
                print(f"! {video_id}: not in videos -- run update_catalog.py first",
                      file=sys.stderr)
                totals["skipped"] += 1
                continue
            if has_whisper(conn, video_id) and not args.redo:
                totals["skipped"] += 1
                continue

            whisper = load_json(whisper_path)
            verdicts = (load_json(verdict_path) if verdict_path
                        else {"rulings": [], "judge": None})
            provenance = f"judge:{verdicts.get('judge') or 'none'}"
            stats = apply_video(conn, video_id, whisper, verdicts, provenance,
                                quiet=args.quiet)
            totals["videos"] += 1
            for key in ("segments", "applied", "queued", "refused",
                        "confirmed", "unmatched"):
                totals[key] += stats.get(key, 0)
            if args.limit and totals["videos"] >= args.limit:
                break

        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    finally:
        conn.close()

    label = "DRY RUN -- nothing written" if args.dry_run else "done"
    print(f"\n{label}: {totals['videos']} videos, {totals['segments']} whisper "
          f"segments, {totals['applied']} corrections applied, "
          f"{totals['queued']} escalations queued, {totals['refused']} refused, "
          f"{totals['confirmed']} confirmed, {totals['skipped']} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())

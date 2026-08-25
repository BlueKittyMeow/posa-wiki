#!/usr/bin/env python3
"""Derive ``videos.number_of_nights`` from title / description evidence.

Trip length is a **video facet**, not a series -- the same shape as
``scripts/derive_seasons.py``, and the same house rule applies: **Unknown
(NULL) is a legitimate value** and this script never guesses to fill the
column.

Owner-approved rules (2026-08-24):

**High confidence** (written straight to ``videos.number_of_nights`` with
``nights_confidence='high'`` and ``nights_source`` recording the rule):

* a title stating nights is exact -- "7 Nights Of Winter Camping" -> 7,
  "Winter Bush Camp with My Dog for 2 Nights" -> 2;
* the part-title form "(Night X of Y)" gives the *trip* length Y, not X;
* a title stating days converts, ``nights = days - 1``. This is validated
  against his own titles: "8 Day Wilderness Adventure with My Dog
  (Night 7 of 7)" pairs an 8-day framing with a 7-night one;
* when a title carries **both** forms they are cross-checked -- consistent
  (``days - 1 == nights``) writes, inconsistent goes to review and is never
  auto-written;
* "Overnight" / "Overnighter" in the title -> 1.

**Medium confidence** (never written; dumped to
``data/nights_review_candidates.json`` for a human pass in
``/admin/review/nights``):

* week language -- "Weeklong", "A Week in the Wilderness", "2 Weeks on Isle
  Royale". A week is 6 or 7 nights depending on how he counts it, and the
  title does not say which;
* membership of a day-trip series ("Hike and Cook", "Day Hiking") with no
  overnight evidence anywhere -> *candidate* 0 nights. **0 is never
  inferred**: the absence of overnight evidence is not evidence of absence,
  so a probable day trip is a proposal, not a write;
* the same patterns found in the first 500 characters of the description;
* an inconsistent days/nights title pair (both readings are proposed).

Never overwrites:

* ``nights_confidence='human'`` is untouchable, full stop.
* an existing value is only re-derived when ``number_of_nights`` is currently
  NULL (so a hand-cleared value is not silently refilled).

Idempotent: a second run writes 0 rows. Rerun it after
``scripts/update_catalog.py`` picks up new uploads.

Usage:
    python scripts/derive_nights.py [--db path] [--dry-run] [--json path]
"""

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DB = str(REPO_ROOT / 'posa_wiki.db')
DEFAULT_JSON = str(REPO_ROOT / 'data' / 'nights_review_candidates.json')

# Human decisions made in /admin/review/nights. Videos the owner already
# ruled on are never proposed again (the queue also filters at display time,
# since this dump is regenerated wholesale on every run).
from services.review_service import (  # noqa: E402  (needs REPO_ROOT on path)
    DEFAULT_NIGHTS_DECISIONS_PATH, load_nights_decisions)

DEFAULT_DECISIONS_JSON = str(DEFAULT_NIGHTS_DECISIONS_PATH)

# How much of the description counts as evidence. Beyond this it is mostly
# gear links, sponsor copy and channel boilerplate -- noise, not evidence.
DESCRIPTION_WINDOW = 500

# Anything longer than this came from a parsing accident ("36 Minutes",
# a price, a temperature), not from a trip.
MAX_NIGHTS = 60

# Series whose videos are day trips by construction. Membership alone only
# *proposes* 0 -- see the module docstring.
DAY_TRIP_SERIES = ('Hike and Cook', 'Day Hiking')

# --- patterns --------------------------------------------------------------
# "(Night 7 of 7)" -- a part title. The trip is Y nights long, not X.
RE_NIGHT_OF = re.compile(r'(?i)\bnight\s+(\d+)\s+of\s+(\d+)\b')
# "7 Nights", "2 Night", "7  Night" (his own double space), "3-Night".
RE_NIGHTS = re.compile(r'(?i)(\d+)\s*[-–]?\s*nights?\b')
# "8 Day Wilderness Adventure", "10 Days (Almost) Alone".
RE_DAYS = re.compile(r'(?i)(\d+)\s*[-–]?\s*days?\b')
# "Overnight", "Overnighter". Deliberately requires a word boundary so it
# never fires inside "7 Night".
RE_OVERNIGHT = re.compile(r'(?i)\bovernight(?:er|ers)?\b')
# Week language: ambiguous between 6 and 7 nights -> review only.
RE_WEEKS = re.compile(r'(?i)(\d+)\s*weeks?\b')
RE_WEEKLONG = re.compile(r'(?i)\bweek-?long\b|\ba week\b')

NIGHTS_PER_WEEK = 7


def _snippet(text, match, width=60):
    """A short window of *text* around *match*, for eyeballing in review."""
    start = max(0, match.start() - width // 2)
    end = min(len(text), match.end() + width // 2)
    prefix = '…' if start > 0 else ''
    suffix = '…' if end < len(text) else ''
    return prefix + text[start:end].strip() + suffix


def _plausible(nights):
    return nights is not None and 0 <= nights <= MAX_NIGHTS


def _scan(text):
    """Return ``{form: (nights, match)}`` for the forms present in *text*."""
    found = {}

    match = RE_NIGHT_OF.search(text)
    if match:
        total = int(match.group(2))
        if _plausible(total):
            found['night_of'] = (total, match)

    match = RE_NIGHTS.search(text)
    if match:
        value = int(match.group(1))
        if _plausible(value):
            found['nights'] = (value, match)

    match = RE_DAYS.search(text)
    if match:
        days = int(match.group(1))
        if _plausible(days) and days >= 1:
            found['days'] = (days - 1, match)

    match = RE_OVERNIGHT.search(text)
    if match:
        found['overnight'] = (1, match)

    match = RE_WEEKS.search(text)
    if match:
        weeks = int(match.group(1))
        if _plausible(weeks * NIGHTS_PER_WEEK):
            found['weeks'] = (weeks * NIGHTS_PER_WEEK, match)
    elif RE_WEEKLONG.search(text):
        found['weeks'] = (NIGHTS_PER_WEEK, RE_WEEKLONG.search(text))

    return found


def classify(row, in_day_trip_series=False):
    """Return ``(high, review)`` for one video row.

    ``high`` is ``(nights, source, evidence)`` or ``None``.
    ``review`` is a list of ``(nights, rule, evidence)`` proposals.
    """
    title = row['title'] or ''
    description = (row['description'] or '')[:DESCRIPTION_WINDOW]
    review = []

    found = _scan(title)

    # -- the stated night count, preferring the explicit part-title form ----
    stated = None
    stated_rule = None
    if 'night_of' in found:
        stated, stated_match = found['night_of']
        stated_rule = 'title:night-of'
    elif 'nights' in found:
        stated, stated_match = found['nights']
        stated_rule = 'title:nights'

    days = found.get('days')

    # -- both forms present: cross-check, never resolve a disagreement -----
    if stated is not None and days is not None:
        converted, days_match = days
        if converted == stated:
            return (stated, f'{stated_rule}+days-cross-check',
                    _snippet(title, stated_match)), review
        # Inconsistent: "10 Day ... (Night 7 of 7)" tells us nothing certain.
        review.append((stated, f'conflict:{stated_rule}',
                       _snippet(title, stated_match)))
        review.append((converted, 'conflict:title:days-minus-one',
                       _snippet(title, days_match)))
        return None, review

    # -- a stated night count is exact -------------------------------------
    if stated is not None:
        return (stated, stated_rule, _snippet(title, stated_match)), review

    # -- days convert: nights = days - 1 -----------------------------------
    if days is not None:
        converted, days_match = days
        if converted == 0:
            # "1 Day ..." would convert to 0, but 0 is never written from an
            # inference -- Unknown (or a human) decides a day trip.
            review.append((0, 'title:days-minus-one',
                           _snippet(title, days_match)))
        else:
            return (converted, 'title:days-minus-one',
                    _snippet(title, days_match)), review

    # -- "Overnight" means one night ---------------------------------------
    if 'overnight' in found:
        nights, match = found['overnight']
        return (nights, 'title:overnight', _snippet(title, match)), review

    # -- medium: week language is 6 or 7, and the title does not say which --
    if 'weeks' in found:
        nights, match = found['weeks']
        review.append((nights, 'title:week-language',
                       _snippet(title, match)
                       + '  (a “week” is 6 or 7 nights — verify)'))

    # -- medium: the same patterns in the description ----------------------
    described = _scan(description)
    for form, rule in (('night_of', 'description:night-of'),
                       ('nights', 'description:nights'),
                       ('days', 'description:days-minus-one'),
                       ('overnight', 'description:overnight')):
        if form in described:
            nights, match = described[form]
            review.append((nights, rule, _snippet(description, match)))

    # -- medium: day-trip series membership --------------------------------
    # Probably 0 nights. "Probably" is a review-tier answer, never a write.
    if in_day_trip_series and not found and not described:
        review.append((0, 'series:day-trip',
                       'member of a day-trip series (Hike and Cook / Day '
                       'Hiking) with no overnight evidence — probably a day '
                       'trip, but verify'))

    # Deduplicate while keeping order.
    seen = set()
    deduped = []
    for nights, rule, evidence in review:
        if (nights, rule) in seen:
            continue
        seen.add((nights, rule))
        deduped.append((nights, rule, evidence))
    return None, deduped


def _day_trip_video_ids(cursor):
    """Video ids belonging to a day-trip series (empty set if unmapped)."""
    marks = ','.join('?' * len(DAY_TRIP_SERIES))
    try:
        rows = cursor.execute(
            'SELECT vs.video_id FROM video_series vs '
            'JOIN series s ON s.series_id = vs.series_id '
            f'WHERE s.name IN ({marks})', DAY_TRIP_SERIES).fetchall()
    except sqlite3.Error:  # pragma: no cover - schema without series tables
        return set()
    return {row[0] for row in rows}


def _bucket(nights):
    """Coarse label used for the run summary."""
    if nights == 0:
        return 'day trip (0)'
    if nights == 1:
        return 'overnight (1)'
    if nights <= 3:
        return 'weekend (2-3)'
    if nights <= 7:
        return 'week-ish (4-7)'
    return 'epic (8+)'


def derive(db_path=DEFAULT_DB, json_path=DEFAULT_JSON, dry_run=False,
           verbose=True, decisions_path=DEFAULT_DECISIONS_JSON):
    """Apply the high-confidence rules; dump review candidates. Returns dict."""
    decisions = load_nights_decisions(decisions_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    videos = cursor.execute(
        'SELECT video_id, title, description, upload_date, '
        'number_of_nights, nights_confidence, nights_source '
        'FROM videos WHERE deleted_at IS NULL'
    ).fetchall()
    day_trip_ids = _day_trip_video_ids(cursor)

    written = Counter()
    review_candidates = []
    written_total = 0
    protected_human = 0
    skipped_existing = 0
    decided_skipped = 0
    samples = []

    for row in videos:
        high, review = classify(
            row, in_day_trip_series=row['video_id'] in day_trip_ids)

        # -- never overwrite -----------------------------------------------
        if row['nights_confidence'] == 'human':
            # A person decided. Untouchable, and no point proposing again.
            protected_human += 1
            continue
        if high is not None:
            nights, source, evidence = high
            if row['number_of_nights'] is not None:
                # An existing value is only re-derived when currently NULL.
                skipped_existing += 1
            else:
                cursor.execute(
                    'UPDATE videos SET number_of_nights = ?, '
                    'nights_confidence = ?, nights_source = ?, updated_at = ? '
                    'WHERE video_id = ?',
                    (nights, 'high', source,
                     datetime.now().isoformat(), row['video_id']),
                )
                if cursor.rowcount:
                    written[nights] += 1
                    written_total += 1
                    samples.append({'video_id': row['video_id'],
                                    'title': row['title'],
                                    'nights': nights, 'source': source,
                                    'evidence': evidence})
            continue

        # -- medium confidence: propose only -------------------------------
        for nights, rule, evidence in review:
            if row['video_id'] in decisions:
                decided_skipped += 1
                continue
            review_candidates.append({
                'video_id': row['video_id'],
                'title': row['title'],
                'upload_date': row['upload_date'],
                'proposed_nights': nights,
                'rule': rule,
                'evidence': evidence,
                'confidence': 'medium',
            })

    if dry_run:
        conn.rollback()
    else:
        conn.commit()

    # Post-run totals across the whole catalogue.
    distribution = {
        row[0]: row[1] for row in cursor.execute(
            'SELECT number_of_nights, COUNT(*) FROM videos '
            'WHERE number_of_nights IS NOT NULL AND deleted_at IS NULL '
            'GROUP BY number_of_nights')
    }
    unknown = cursor.execute(
        'SELECT COUNT(*) FROM videos WHERE number_of_nights IS NULL '
        'AND deleted_at IS NULL').fetchone()[0]
    conn.close()

    payload = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'database': db_path,
        'count': len(review_candidates),
        'note': 'Medium-confidence trip-length proposals only. Nothing here '
                'has been written to the database; a human decides (see '
                '/admin/review/nights). Unknown is a legitimate answer -- '
                'reject anything that is not actually evident. 0 nights is '
                'never inferred, only proposed.',
        'already_decided_skipped': decided_skipped,
        'candidates': review_candidates,
    }
    if not dry_run and json_path:
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_path).write_text(json.dumps(payload, indent=2) + '\n')

    if verbose:
        print(f'🌙 derive_nights over {len(videos)} videos in {db_path}'
              + ('  (dry run)' if dry_run else ''))
        print(f'\n   Written this run: {written_total}')

        print('\n   Trip-length distribution (whole catalogue):')
        for nights in sorted(distribution):
            print(f'      {nights:>3} night{"s" if nights != 1 else " "}  '
                  f'{distribution[nights]:>4}   [{_bucket(nights)}]')
        print(f'      {"unknown":>9}  {unknown:>4}')

        by_nights = Counter(c['proposed_nights'] for c in review_candidates)
        print(f'\n   Review candidates: {len(review_candidates)}'
              + ('' if dry_run else f' -> {json_path}'))
        for nights, count in sorted(by_nights.items()):
            print(f'      ? {nights:>3} nights  {count}')

        if protected_human:
            print(f'\n   Protected (human decisions): {protected_human}')
        if skipped_existing:
            print(f'   Left alone (already had a length): {skipped_existing}')
        if decided_skipped:
            print(f'   Skipped (already decided in /admin): {decided_skipped}')

        if samples:
            print('\n   Sample assignments:')
            for sample in samples[:10]:
                print(f'      {sample["nights"]:>3} ← {sample["title"][:58]}'
                      f'   [{sample["source"]}]')

    return {
        'videos_scanned': len(videos),
        'written_total': written_total,
        'written_by_nights': dict(written),
        'distribution': distribution,
        'unknown': unknown,
        'review_candidates': len(review_candidates),
        'review_by_nights': dict(Counter(
            c['proposed_nights'] for c in review_candidates)),
        'protected_human': protected_human,
        'skipped_existing': skipped_existing,
        'already_decided_skipped': decided_skipped,
        'samples': samples,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=DEFAULT_DB, help='database path')
    parser.add_argument('--json', default=DEFAULT_JSON,
                        help='review-candidate output path')
    parser.add_argument('--dry-run', action='store_true',
                        help='roll back and skip the JSON dump')
    parser.add_argument('--decisions', default=DEFAULT_DECISIONS_JSON,
                        help='human review decisions to skip')
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args()

    derive(args.db, args.json, dry_run=args.dry_run, verbose=not args.quiet,
           decisions_path=args.decisions)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

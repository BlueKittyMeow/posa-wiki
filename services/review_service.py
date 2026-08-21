"""Review-queue framework for the /admin review UI.

Replaces the old "an agent pastes a list of proposals, the owner replies by
number" flow with something the owner can click through.

A *queue* is a small class that knows how to

* ``items(conn)``   -- yield the pending :class:`ReviewItem` proposals
* ``approve(conn, payload)`` -- write the accepted proposal to the database
  (with ``human:web-review`` provenance wherever the target table has a notes
  column) and remember the decision so it never comes back
* ``reject(conn, payload)``  -- remember the decision only

Every queue is registered in :data:`QUEUES`; adding a fourth queue later is one
class plus one registry entry -- the routes and templates are generic.

Decisions are persisted as JSON under ``DATA_DIR`` (config key, so tests can
point it at a tmp dir) rather than in the database, because the *proposals*
themselves live in regenerable JSON dumps produced by ``scripts/assign_series.py``.
Filtering at display time is the robust approach: the candidates file is
rewritten wholesale on every run of that script.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import current_app

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Provenance stamped into notes columns for anything a human approved here.
REVIEW_PROVENANCE = 'human:web-review'

SERIES_CANDIDATES_FILENAME = 'series_review_candidates.json'
SERIES_DECISIONS_FILENAME = 'series_review_decisions.json'
TAG_DISMISSED_FILENAME = 'tag_review_dismissed.json'
DOG_DISMISSED_FILENAME = 'dog_review_dismissed.json'

DEFAULT_DATA_DIR = REPO_ROOT / 'data'
DEFAULT_DECISIONS_PATH = DEFAULT_DATA_DIR / SERIES_DECISIONS_FILENAME

MAX_TAG_SAMPLES = 6


# --------------------------------------------------------------------------
# JSON helpers
# --------------------------------------------------------------------------

def read_json(path, default=None):
    """Return the parsed JSON at *path*, or *default* when absent/corrupt."""
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            return json.load(handle)
    except (FileNotFoundError, ValueError, OSError):
        return default


def write_json(path, payload):
    """Write *payload* to *path* atomically (tmp file + rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, indent=2)
            handle.write('\n')
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)  # our own scratch file, never user data
        raise


def data_dir() -> Path:
    """Directory holding the review JSON files (config-overridable)."""
    try:
        configured = current_app.config.get('DATA_DIR')
    except RuntimeError:  # outside an app context (scripts)
        configured = None
    return Path(configured) if configured else DEFAULT_DATA_DIR


def data_path(filename: str) -> Path:
    return data_dir() / filename


def tag_authority_path() -> Path:
    try:
        configured = current_app.config.get('TAG_AUTHORITY_PATH')
    except RuntimeError:
        configured = None
    return Path(configured) if configured else REPO_ROOT / 'tag_authority_system.json'


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


# --------------------------------------------------------------------------
# Series decisions -- shared with scripts/assign_series.py
# --------------------------------------------------------------------------

def series_decision_key(video_id: str, series_name: str) -> str:
    """Stable key for a (video, proposed series) pair."""
    return f'{video_id}|{series_name}'


def load_series_decisions(path=None) -> Dict[str, Any]:
    """Return ``{key: decision-record}`` for already-reviewed series pairs.

    Importable from plain scripts (no Flask app context required) so
    ``scripts/assign_series.py`` can skip pairs the owner already ruled on.
    """
    if path is None:
        path = DEFAULT_DECISIONS_PATH
    payload = read_json(path, default={}) or {}
    decisions = payload.get('decisions')
    return decisions if isinstance(decisions, dict) else {}


def record_series_decision(video_id, series_name, decision, extra=None,
                           path=None):
    """Persist an approve/reject for a (video, series) pair."""
    if path is None:
        path = data_path(SERIES_DECISIONS_FILENAME)
    payload = read_json(path, default=None) or {}
    decisions = payload.get('decisions')
    if not isinstance(decisions, dict):
        decisions = {}
    record = {
        'video_id': video_id,
        'series': series_name,
        'decision': decision,
        'decided_at': _now(),
        'source': REVIEW_PROVENANCE,
    }
    if extra:
        record.update(extra)
    decisions[series_decision_key(video_id, series_name)] = record
    payload['decisions'] = decisions
    payload['updated_at'] = _now()
    payload.setdefault(
        'note',
        'Human decisions from the /admin review queue. assign_series.py reads '
        'this file so decided pairs are never proposed again.',
    )
    write_json(path, payload)
    return record


def _load_dismissed(filename) -> List[str]:
    payload = read_json(data_path(filename), default=None) or {}
    dismissed = payload.get('dismissed')
    return [str(x) for x in dismissed] if isinstance(dismissed, list) else []


def _record_dismissal(filename, value, extra=None):
    path = data_path(filename)
    payload = read_json(path, default=None) or {}
    dismissed = payload.get('dismissed')
    if not isinstance(dismissed, list):
        dismissed = []
    if value not in dismissed:
        dismissed.append(value)
    payload['dismissed'] = dismissed
    payload['updated_at'] = _now()
    history = payload.get('history')
    if not isinstance(history, list):
        history = []
    entry = {'value': value, 'dismissed_at': _now(),
             'source': REVIEW_PROVENANCE}
    if extra:
        entry.update(extra)
    history.append(entry)
    payload['history'] = history
    write_json(path, payload)
    return entry


# --------------------------------------------------------------------------
# Items and the queue base class
# --------------------------------------------------------------------------

@dataclass
class ReviewItem:
    """One reviewable proposal, rendered as a card."""

    kind: str
    item_id: str                      # unique within the queue
    title: str
    proposal: str                     # what is being proposed
    provenance: str                   # the rule / why it was proposed
    payload: Dict[str, Any] = field(default_factory=dict)
    video_id: Optional[str] = None
    thumbnail_url: Optional[str] = None
    upload_date: Optional[str] = None
    detail: Optional[str] = None      # extra line (counts etc.)
    samples: List[str] = field(default_factory=list)

    @property
    def payload_json(self) -> str:
        return json.dumps(self.payload, sort_keys=True)


class ReviewQueue:
    """Base class -- subclasses implement items/approve/reject."""

    key = ''
    label = ''
    icon = '📋'
    description = ''
    empty_message = 'Nothing to review. 🎉'

    def items(self, conn) -> List[ReviewItem]:
        raise NotImplementedError

    def count(self, conn) -> int:
        return len(self.items(conn))

    def approve(self, conn, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def reject(self, conn, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


# --------------------------------------------------------------------------
# 1. Series candidates
# --------------------------------------------------------------------------

def _retired_series_names():
    """Series the owner explicitly retired (never propose them again)."""
    try:
        from scripts.seed_series import RETIRED_SERIES
        return {name for name in RETIRED_SERIES}
    except Exception:  # pragma: no cover - seed script always importable
        return set()


class SeriesCandidateQueue(ReviewQueue):
    """Medium-confidence series proposals from ``scripts/assign_series.py``."""

    key = 'series'
    label = 'Series candidates'
    icon = '📺'
    description = ('Medium-confidence series proposals. Approving writes a '
                   'video_series row stamped ' + REVIEW_PROVENANCE + '.')
    empty_message = ('No pending series candidates. Regenerate them with '
                     'python scripts/assign_series.py.')

    def _candidates(self):
        payload = read_json(data_path(SERIES_CANDIDATES_FILENAME), default=None)
        if not payload:
            return None  # signals "file missing"
        candidates = payload.get('candidates')
        return candidates if isinstance(candidates, list) else []

    def file_missing(self) -> bool:
        return self._candidates() is None

    def items(self, conn) -> List[ReviewItem]:
        candidates = self._candidates()
        if not candidates:
            return []

        series_ids = {
            row['name']: row['series_id']
            for row in conn.execute('SELECT series_id, name FROM series')
        }
        retired = _retired_series_names()
        decisions = load_series_decisions(data_path(SERIES_DECISIONS_FILENAME))

        existing = {
            (row['video_id'], row['series_id'])
            for row in conn.execute('SELECT video_id, series_id FROM video_series')
        }

        video_ids = [c.get('video_id') for c in candidates if c.get('video_id')]
        videos = {}
        if video_ids:
            marks = ','.join('?' * len(video_ids))
            videos = {
                row['video_id']: row
                for row in conn.execute(
                    'SELECT video_id, title, upload_date, thumbnail_url '
                    f'FROM videos WHERE video_id IN ({marks})', video_ids)
            }

        items = []
        for candidate in candidates:
            video_id = candidate.get('video_id')
            name = candidate.get('proposed_series')
            if not video_id or not name:
                continue
            # Retired series (e.g. Michigan Adventures) and series that simply
            # do not exist in this database must never be proposed.
            if name in retired or name not in series_ids:
                continue
            if series_decision_key(video_id, name) in decisions:
                continue
            if (video_id, series_ids[name]) in existing:
                continue
            video = videos.get(video_id)
            if video is None:
                continue

            items.append(ReviewItem(
                kind='series',
                item_id=series_decision_key(video_id, name),
                title=video['title'] or candidate.get('title') or video_id,
                proposal=f'Add to series “{name}”',
                provenance='rule: ' + (candidate.get('rule') or 'unknown')
                           + f" ({candidate.get('confidence', 'medium')} confidence)",
                payload={'video_id': video_id, 'series': name},
                video_id=video_id,
                thumbnail_url=video['thumbnail_url'],
                upload_date=video['upload_date'],
            ))
        return items

    # -- actions ----------------------------------------------------------
    def _resolve(self, conn, payload):
        video_id = (payload.get('video_id') or '').strip()
        name = (payload.get('series') or '').strip()
        if not video_id or not name:
            raise ValueError('Missing video_id or series.')
        if name in _retired_series_names():
            raise ValueError(f'Series “{name}” has been retired.')
        row = conn.execute('SELECT series_id FROM series WHERE name = ?',
                           (name,)).fetchone()
        if row is None:
            raise ValueError(f'Series “{name}” does not exist.')
        return video_id, name, row['series_id']

    def approve(self, conn, payload):
        video_id, name, series_id = self._resolve(conn, payload)
        conn.execute(
            'INSERT OR IGNORE INTO video_series '
            '(video_id, series_id, episode_number, trip_id, notes) '
            'VALUES (?, ?, NULL, NULL, ?)',
            (video_id, series_id, REVIEW_PROVENANCE),
        )
        conn.commit()
        record_series_decision(video_id, name, 'approve',
                               extra={'series_id': series_id},
                               path=data_path(SERIES_DECISIONS_FILENAME))
        return {
            'message': f'Added “{name}” to {video_id}.',
            'resource_id': video_id,
            'details': {'video_id': video_id, 'series': name,
                        'series_id': series_id, 'notes': REVIEW_PROVENANCE},
        }

    def reject(self, conn, payload):
        video_id, name, series_id = self._resolve(conn, payload)
        record_series_decision(video_id, name, 'reject',
                               extra={'series_id': series_id},
                               path=data_path(SERIES_DECISIONS_FILENAME))
        return {
            'message': f'Dismissed “{name}” for {video_id}.',
            'resource_id': video_id,
            'details': {'video_id': video_id, 'series': name},
        }


# --------------------------------------------------------------------------
# 2. Unvalidated tags
# --------------------------------------------------------------------------

class UnvalidatedTagQueue(ReviewQueue):
    """Distinct ``videos.unvalidated_tags`` values awaiting an authority."""

    key = 'tags'
    label = 'Unvalidated tags'
    icon = '🏷️'
    description = ('YouTube tags with no authority yet. Approving creates an '
                   'authority in tag_authority_system.json and re-runs the '
                   'validation split for the affected videos.')
    empty_message = 'Every tag has an authority (or has been dismissed).'

    def _aggregate(self, conn):
        dismissed = set(_load_dismissed(TAG_DISMISSED_FILENAME))
        buckets = {}
        rows = conn.execute(
            "SELECT video_id, title, upload_date, thumbnail_url, unvalidated_tags "
            "FROM videos "
            "WHERE unvalidated_tags IS NOT NULL "
            "AND unvalidated_tags NOT IN ('', 'null', '[]')"
        )
        for row in rows:
            try:
                tags = json.loads(row['unvalidated_tags']) or []
            except (ValueError, TypeError):
                continue
            for tag in tags:
                if not isinstance(tag, str):
                    continue
                tag = tag.strip()
                if not tag or tag.lower() in dismissed or tag in dismissed:
                    continue
                bucket = buckets.setdefault(tag, {'count': 0, 'samples': [],
                                                  'first': row})
                bucket['count'] += 1
                if len(bucket['samples']) < MAX_TAG_SAMPLES:
                    bucket['samples'].append(row['title'])
        return buckets

    def items(self, conn) -> List[ReviewItem]:
        buckets = self._aggregate(conn)
        items = []
        for tag, bucket in sorted(buckets.items(),
                                  key=lambda kv: (-kv[1]['count'], kv[0])):
            row = bucket['first']
            items.append(ReviewItem(
                kind='tag',
                item_id=f'tag:{tag}',
                title=tag,
                proposal=f'Promote to authority “{tag.title()}”',
                provenance=f'unvalidated YouTube tag on {bucket["count"]} '
                           f'video{"s" if bucket["count"] != 1 else ""}',
                payload={'tag': tag},
                video_id=row['video_id'],
                thumbnail_url=row['thumbnail_url'],
                upload_date=row['upload_date'],
                detail=f'{bucket["count"]} video'
                       f'{"s" if bucket["count"] != 1 else ""}',
                samples=bucket['samples'],
            ))
        return items

    # -- actions ----------------------------------------------------------
    def approve(self, conn, payload):
        tag = (payload.get('tag') or '').strip()
        if not tag:
            raise ValueError('Missing tag.')

        canonical = tag.title()
        path = tag_authority_path()
        authority_data = read_json(path, default=None)
        if not authority_data or 'authorities' not in authority_data:
            raise ValueError(f'Tag authority file not found at {path}.')

        authorities = authority_data['authorities']
        existing = next(
            (a for a in authorities
             if a.get('canonical_name', '').lower() == canonical.lower()),
            None,
        )
        if existing is not None:
            aliases = existing.setdefault('aliases', [])
            if tag.lower() not in [a.lower() for a in aliases]:
                aliases.append(tag.lower())
            created = False
        else:
            authorities.append({
                'canonical_name': canonical,
                'category': 'review',
                'aliases': [tag.lower()],
                'description': f'Promoted from tag review ({REVIEW_PROVENANCE})',
            })
            created = True

        analysis = authority_data.get('analysis')
        if isinstance(analysis, dict):
            analysis['total_authorities'] = len(authorities)
            analysis['total_aliases'] = sum(
                len(a.get('aliases', [])) for a in authorities)
        write_json(path, authority_data)

        updated = revalidate_videos_for_tag(conn, tag, authority_path=path)

        return {
            'message': (f'Promoted “{tag}” to authority “{canonical}” '
                        f'({updated} video{"s" if updated != 1 else ""} '
                        're-validated).'),
            'resource_id': tag,
            'details': {'tag': tag, 'canonical_name': canonical,
                        'authority_created': created,
                        'videos_revalidated': updated},
        }

    def reject(self, conn, payload):
        tag = (payload.get('tag') or '').strip()
        if not tag:
            raise ValueError('Missing tag.')
        _record_dismissal(TAG_DISMISSED_FILENAME, tag)
        return {
            'message': f'Dismissed tag “{tag}”; it will not be proposed again.',
            'resource_id': tag,
            'details': {'tag': tag},
        }


def revalidate_videos_for_tag(conn, tag, authority_path=None):
    """Re-run the validated/unvalidated split for videos carrying *tag*.

    Reuses ``revalidate_database_tags`` rather than duplicating its logic.
    """
    import revalidate_database_tags as revalidate

    if authority_path is None:
        authority_path = tag_authority_path()
    alias_to_authority = revalidate.load_tag_authorities(str(authority_path))

    needle = tag.lower()
    updated = 0
    rows = conn.execute(
        "SELECT video_id, youtube_tags, validated_tags, unvalidated_tags "
        "FROM videos WHERE youtube_tags IS NOT NULL AND youtube_tags != '[]'"
    ).fetchall()

    for row in rows:
        try:
            original = json.loads(row['youtube_tags']) or []
        except (ValueError, TypeError):
            continue
        if not any(isinstance(t, str) and t.strip().lower() == needle
                   for t in original):
            continue

        new_validated, new_unvalidated = revalidate.validate_tags(
            original, alias_to_authority)
        try:
            cur_validated = json.loads(row['validated_tags'] or '[]')
            cur_unvalidated = json.loads(row['unvalidated_tags'] or '[]')
        except (ValueError, TypeError):
            cur_validated, cur_unvalidated = [], []

        if (set(new_validated) != set(cur_validated)
                or set(new_unvalidated) != set(cur_unvalidated)):
            conn.execute(
                'UPDATE videos SET validated_tags = ?, unvalidated_tags = ?, '
                'updated_at = ? WHERE video_id = ?',
                (json.dumps(new_validated), json.dumps(new_unvalidated),
                 datetime.now().isoformat(), row['video_id']),
            )
            updated += 1

    conn.commit()
    return updated


# --------------------------------------------------------------------------
# 3. Dog candidates (the "Layla rule")
# --------------------------------------------------------------------------

class DogCandidateQueue(ReviewQueue):
    """Videos with Lucas but no Layla -- she is usually with him."""

    key = 'dogs'
    label = 'Dog candidates'
    icon = '🐕'
    description = ('The Layla rule: Lucas appears, so Layla probably does too. '
                   'Approving links the dog with a provenance note.')
    empty_message = 'No Lucas videos are missing Layla.'

    PERSON_NAME = 'Lucas'
    DOG_NAME = 'Layla'
    NOTE = f'{REVIEW_PROVENANCE} (Layla rule: Lucas is present)'

    def _ids(self, conn):
        person = conn.execute(
            'SELECT person_id FROM people WHERE canonical_name = ?',
            (self.PERSON_NAME,)).fetchone()
        dog = conn.execute('SELECT dog_id FROM dogs WHERE name = ?',
                           (self.DOG_NAME,)).fetchone()
        if person is None or dog is None:
            return None, None
        return person['person_id'], dog['dog_id']

    def items(self, conn) -> List[ReviewItem]:
        person_id, dog_id = self._ids(conn)
        if person_id is None:
            return []
        dismissed = set(_load_dismissed(DOG_DISMISSED_FILENAME))

        rows = conn.execute(
            '''
            SELECT v.video_id, v.title, v.upload_date, v.thumbnail_url
            FROM videos v
            JOIN video_people vp ON vp.video_id = v.video_id
            WHERE vp.person_id = ?
              AND v.deleted_at IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM video_dogs vd
                  WHERE vd.video_id = v.video_id AND vd.dog_id = ?
              )
            ORDER BY v.upload_date DESC
            ''', (person_id, dog_id)).fetchall()

        items = []
        for row in rows:
            if row['video_id'] in dismissed:
                continue
            items.append(ReviewItem(
                kind='dog',
                item_id=f'dog:{row["video_id"]}',
                title=row['title'],
                proposal=f'{self.DOG_NAME} may appear ({self.PERSON_NAME} '
                         'is present)',
                provenance='rule: layla-follows-lucas',
                payload={'video_id': row['video_id']},
                video_id=row['video_id'],
                thumbnail_url=row['thumbnail_url'],
                upload_date=row['upload_date'],
            ))
        return items

    # -- actions ----------------------------------------------------------
    def approve(self, conn, payload):
        video_id = (payload.get('video_id') or '').strip()
        if not video_id:
            raise ValueError('Missing video_id.')
        person_id, dog_id = self._ids(conn)
        if dog_id is None:
            raise ValueError(f'{self.DOG_NAME} or {self.PERSON_NAME} is not '
                             'in this database.')
        linked = conn.execute(
            'SELECT 1 FROM video_people WHERE video_id = ? AND person_id = ?',
            (video_id, person_id)).fetchone()
        if linked is None:
            raise ValueError(f'{self.PERSON_NAME} is not linked to {video_id}.')

        conn.execute(
            'INSERT OR IGNORE INTO video_dogs (video_id, dog_id, role, notes) '
            'VALUES (?, ?, ?, ?)',
            (video_id, dog_id, 'companion', self.NOTE),
        )
        conn.commit()
        return {
            'message': f'Linked {self.DOG_NAME} to {video_id}.',
            'resource_id': video_id,
            'details': {'video_id': video_id, 'dog_id': dog_id,
                        'notes': self.NOTE},
        }

    def reject(self, conn, payload):
        video_id = (payload.get('video_id') or '').strip()
        if not video_id:
            raise ValueError('Missing video_id.')
        _record_dismissal(DOG_DISMISSED_FILENAME, video_id,
                          extra={'rule': 'layla-follows-lucas'})
        return {
            'message': f'Dismissed {self.DOG_NAME} for {video_id}.',
            'resource_id': video_id,
            'details': {'video_id': video_id},
        }


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

QUEUES: Dict[str, ReviewQueue] = {
    queue.key: queue
    for queue in (SeriesCandidateQueue(), UnvalidatedTagQueue(),
                  DogCandidateQueue())
}


def get_queue(key) -> Optional[ReviewQueue]:
    return QUEUES.get(key)


def queue_summaries(conn) -> List[Dict[str, Any]]:
    """``[{key, label, icon, description, count}, ...]`` for the dashboard."""
    summaries = []
    for queue in QUEUES.values():
        summaries.append({
            'key': queue.key,
            'label': queue.label,
            'icon': queue.icon,
            'description': queue.description,
            'count': queue.count(conn),
        })
    return summaries

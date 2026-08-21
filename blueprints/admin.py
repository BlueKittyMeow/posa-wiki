"""Admin panel blueprint -- review queues first.

Phase 2B Step 2 was reshaped by the owner: instead of user-management CRUD,
the centrepiece is a **review queue UI** that replaces the old "an agent pastes
a list of proposals, the owner replies by number" workflow.

Routes:

* ``GET  /admin``                            -- dashboard (queue counts + stats)
* ``GET  /admin/review/<queue>``             -- card grid of pending proposals
* ``POST /admin/review/<queue>/<action>``    -- approve / reject (CSRF-protected)

The queues themselves live in :mod:`services.review_service`; adding a fourth
one is a class plus a registry entry -- nothing here changes.
"""

import json

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user

from db import get_db
from services.audit_log_service import create_audit_log
from services.review_service import QUEUES, get_queue, queue_summaries
from utils.decorators import editor_required

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

VALID_ACTIONS = ('approve', 'reject')


def _dashboard_stats(conn):
    """Cheap headline numbers for the dashboard."""

    def scalar(sql, default=0):
        try:
            row = conn.execute(sql).fetchone()
        except Exception:  # table may not exist in older databases
            return default
        return row[0] if row and row[0] is not None else default

    return {
        'videos': scalar('SELECT COUNT(*) FROM videos'),
        'people': scalar('SELECT COUNT(*) FROM people'),
        'dogs': scalar('SELECT COUNT(*) FROM dogs'),
        'series': scalar('SELECT COUNT(*) FROM series'),
        'series_memberships': scalar('SELECT COUNT(*) FROM video_series'),
        'transcript_segments': scalar('SELECT COUNT(*) FROM transcript_segments'),
        'transcribed_videos': scalar(
            'SELECT COUNT(DISTINCT video_id) FROM transcript_segments'),
        'newest_upload': scalar('SELECT MAX(upload_date) FROM videos', None),
        'last_catalog_touch': scalar('SELECT MAX(updated_at) FROM videos', None),
        'audit_events': scalar('SELECT COUNT(*) FROM audit_logs'),
    }


@admin_bp.route('/')
@editor_required
def dashboard():
    """Landing page: what needs reviewing, plus a few catalogue stats."""
    conn = get_db()
    summaries = queue_summaries(conn)

    # Every queue fed from a regenerable JSON dump can report the file as
    # missing; the dashboard lists them all rather than just series.
    missing_files = [
        {'file': queue.candidates_file,
         'command': queue.regenerate_command}
        for queue in QUEUES.values()
        if queue.candidates_file and queue.file_missing()
    ]

    return render_template(
        'admin/dashboard.html',
        queues=summaries,
        stats=_dashboard_stats(conn),
        pending_total=sum(q['count'] for q in summaries),
        missing_files=missing_files,
    )


@admin_bp.route('/review/<queue_key>')
@editor_required
def review_queue(queue_key):
    """Card grid of pending proposals for one queue."""
    queue = get_queue(queue_key)
    if queue is None:
        abort(404)

    conn = get_db()
    items = queue.items(conn)

    per_page = current_app.config.get('REVIEW_ITEMS_PER_PAGE', 30)
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = min(page, total_pages)
    visible = items[(page - 1) * per_page: page * per_page]

    candidates_missing = bool(queue.candidates_file) and queue.file_missing()

    return render_template(
        'admin/review_queue.html',
        queue=queue,
        items=visible,
        total=len(items),
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        candidates_missing=candidates_missing,
    )


def _posted_payloads():
    """Return the decoded ``payload`` hidden fields from the form."""
    payloads = []
    for raw in request.form.getlist('payload'):
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(decoded, dict):
            payloads.append(decoded)
    return payloads


@admin_bp.route('/review/<queue_key>/<action>', methods=['POST'])
@editor_required
def review_action(queue_key, action):
    """Apply approve/reject to one item (or every item in a bulk form)."""
    queue = get_queue(queue_key)
    if queue is None or action not in VALID_ACTIONS:
        abort(404)

    payloads = _posted_payloads()
    if not payloads:
        flash('Nothing to act on -- the form carried no proposal.', 'error')
        return _back(queue_key)

    conn = get_db()
    handler = getattr(queue, action)

    applied, failed, messages = 0, 0, []
    for payload in payloads:
        try:
            result = handler(conn, payload)
        except Exception as exc:  # a stale card, a retired series, ...
            failed += 1
            current_app.logger.warning('review %s/%s failed: %s',
                                       queue_key, action, exc)
            messages.append(str(exc))
            continue

        applied += 1
        messages.append(result.get('message', ''))
        create_audit_log(
            event_type=f'review.{queue_key}.{action}',
            resource_type=queue.key,
            resource_id=result.get('resource_id'),
            details={
                'queue': queue_key,
                'action': action,
                'proposal': payload,
                'reviewer': getattr(current_user, 'username', None),
                **(result.get('details') or {}),
            },
        )

    if applied and len(payloads) == 1 and not failed:
        flash(messages[0], 'success')
    elif applied:
        flash(f'{action.title()}d {applied} item'
              f'{"s" if applied != 1 else ""}.'
              + (f' {failed} failed.' if failed else ''),
              'success' if not failed else 'error')
    else:
        flash('Nothing applied: ' + '; '.join(m for m in messages if m),
              'error')

    return _back(queue_key)


def _back(queue_key):
    """Redirect back to the queue page the action was fired from."""
    target = request.form.get('next')
    if target and target.startswith('/'):
        return redirect(target)
    return redirect(url_for('admin.review_queue', queue_key=queue_key))

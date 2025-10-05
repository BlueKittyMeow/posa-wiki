"""Role-based access control decorators for Posa Wiki"""
from functools import wraps
from flask import flash, redirect, url_for, abort
from flask_login import current_user


def admin_required(f):
    """Decorator to require admin role

    Usage:
        @app.route('/admin/users')
        @login_required
        @admin_required
        def manage_users():
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))

        if not current_user.is_admin():
            flash('Admin access required.', 'error')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


def editor_required(f):
    """Decorator to require editor or admin role

    Usage:
        @app.route('/edit/video/<video_id>')
        @login_required
        @editor_required
        def edit_video(video_id):
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))

        if not current_user.is_editor():
            flash('Editor or admin access required.', 'error')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function

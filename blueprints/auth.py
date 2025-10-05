"""Authentication blueprint for login/logout functionality"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from flask_login import login_user, logout_user, login_required, current_user
import sqlite3
from models.user import User


auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def get_db_connection():
    """Get database connection (imported from app context)"""
    from flask import current_app
    conn = sqlite3.connect(current_app.config['DATABASE_PATH'])
    conn.row_factory = sqlite3.Row
    return conn


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and handler

    Note: CSRF protection will be added in Step 6 by Codex
    """
    # Redirect if already logged in
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)

        if not username or not password:
            flash('Please provide both username and password.', 'error')
            return render_template('auth/login.html')

        # Load user from database
        conn = get_db_connection()
        user = User.get_by_username(username, conn)

        if user and user.check_password(password):
            # Valid credentials - log in
            login_user(user, remember=remember)

            # Update last login timestamp
            user.update_last_login(conn)
            conn.close()

            # Redirect to next page or home
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('index'))

        # Invalid credentials
        conn.close()
        flash('Invalid username or password.', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Log out current user"""
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))


@auth_bp.route('/profile')
@login_required
def profile():
    """User profile page (placeholder for Phase 2B)"""
    return render_template('auth/profile.html', user=current_user)

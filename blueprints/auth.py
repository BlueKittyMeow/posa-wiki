"""Authentication blueprint for login/logout functionality"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from flask_login import login_user, logout_user, login_required, current_user
import sqlite3
from models.user import User
from forms.auth import LoginForm


auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def get_db_connection():
    """Get database connection (imported from app context)"""
    from flask import current_app
    conn = sqlite3.connect(current_app.config['DATABASE_PATH'])
    conn.row_factory = sqlite3.Row
    return conn


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and handler with CSRF-protected form
    """
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()

    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data
        remember = form.remember_me.data

        conn = get_db_connection()
        user = User.get_by_username(username, conn)

        if user and user.check_password(password):
            login_user(user, remember=remember)
            user.update_last_login(conn)
            conn.close()

            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('index'))

        conn.close()
        flash('Invalid username or password.', 'error')
    elif form.is_submitted():
        flash('Please correct the errors in the form.', 'error')

    return render_template('auth/login.html', form=form)


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

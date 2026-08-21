"""Authentication blueprint for login/logout functionality"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from db import get_db
from models.user import User
from forms.auth import LoginForm
from services.audit_log_service import create_audit_log
from services.rate_limit_service import limiter, per_ip_key


auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", key_func=per_ip_key())
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

        conn = get_db()
        user = User.get_by_username(username, conn)

        if user and user.check_password(password):
            login_user(user, remember=remember)
            user.update_last_login(conn)
            create_audit_log('login_success', resource_type='user', resource_id=user.user_id)

            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('index'))

        create_audit_log('login_failure', severity='WARNING', details={'username': username})
        flash('Invalid username or password.', 'error')
    elif form.is_submitted():
        flash('Please correct the errors in the form.', 'error')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    """Log out current user"""
    create_audit_log('logout', resource_type='user', resource_id=current_user.get_id())
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))


@auth_bp.route('/profile')
@login_required
def profile():
    """User profile page (placeholder for Phase 2B)"""
    return render_template('auth/profile.html', user=current_user)

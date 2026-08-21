"""Rate limiting utilities using Flask-Limiter."""

from typing import Optional
from flask import request, jsonify
from flask_login import current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Limiter instance (initialized without app; configure via init_rate_limiter)
limiter = Limiter(
    key_func=lambda: _user_or_ip_key(),
    default_limits=[]
)


def _user_or_ip_key() -> str:
    """Return limiter key using user ID when available, otherwise client IP."""
    if current_user and current_user.is_authenticated:
        return f"user:{current_user.get_id()}"
    # fall back to remote address helper (supports proxies)
    return f"ip:{get_remote_address()}"


def init_rate_limiter(app):
    """Initialize Flask-Limiter with application configuration."""
    if not app.config.get('RATELIMIT_ENABLED', True):
        app.logger.info('Rate limiting disabled via configuration.')
        return

    storage_uri: Optional[str] = app.config.get('RATELIMIT_STORAGE_URI')
    if not storage_uri:
        storage_uri = app.config['REDIS_URL'] if app.config.get('REDIS_ENABLED') else 'memory://'
        app.config['RATELIMIT_STORAGE_URI'] = storage_uri

    default_limits = [
        limit.strip()
        for limit in app.config.get('RATELIMIT_DEFAULT', '').split(';')
        if limit.strip()
    ]

    app.config.setdefault('RATELIMIT_STRATEGY', 'fixed-window')
    app.config.setdefault('RATELIMIT_SWALLOW_ERRORS', True)

    limiter.init_app(app)

    if default_limits:
        limiter.default_limits = default_limits

    @app.errorhandler(429)
    def handle_rate_limit(e):
        """Return JSON response for rate limit violations."""
        return jsonify({
            'error': 'rate_limited',
            'message': 'Too many requests. Please slow down.'
        }), 429


def per_ip_key():
    """Return a key function that limits purely by IP address."""
    return get_remote_address

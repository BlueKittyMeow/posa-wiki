"""
JWT Authentication Service

Handles JWT token generation, validation, and blacklisting for API authentication.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from flask import current_app

logger = logging.getLogger(__name__)


class RedisTokenStore:
    """
    Manages JWT token blacklist using Redis.
    Falls back gracefully if Redis is unavailable (dev mode).
    """

    def __init__(self):
        self._redis = None
        self._enabled = False

    def init_app(self, app):
        """Initialize Redis connection from Flask app config"""
        if not app.config.get('REDIS_ENABLED', False):
            logger.info('Redis disabled, JWT blacklist will not persist across restarts')
            return

        try:
            import redis
            redis_url = app.config.get('REDIS_URL', 'redis://localhost:6379/0')
            self._redis = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            # Test connection
            self._redis.ping()
            self._enabled = True
            logger.info(f'Redis connected successfully: {redis_url}')
        except Exception as e:
            logger.warning(f'Redis connection failed: {e}. Blacklist will not persist.')
            self._redis = None
            self._enabled = False

    def is_token_blacklisted(self, jti: str) -> bool:
        """Check if a token JTI is blacklisted"""
        if not self._enabled or not self._redis:
            # If Redis is disabled, can't check blacklist - allow token
            return False

        try:
            return self._redis.exists(f'jwt:blacklist:{jti}') > 0
        except Exception as e:
            logger.error(f'Redis blacklist check failed: {e}')
            # Fail open - allow the token rather than blocking all requests
            return False

    def blacklist_token(self, jti: str, expires_in: int):
        """
        Add a token JTI to the blacklist.

        Args:
            jti: JWT ID (unique token identifier)
            expires_in: Seconds until the token expires (for TTL)
        """
        if not self._enabled or not self._redis:
            logger.debug(f'Redis disabled, cannot blacklist token {jti}')
            return

        try:
            key = f'jwt:blacklist:{jti}'
            self._redis.setex(key, expires_in, '1')
            logger.info(f'Token blacklisted: {jti}')
        except Exception as e:
            logger.error(f'Redis blacklist failed: {e}')

    def cleanup_expired(self):
        """
        Redis automatically removes expired keys, so this is a no-op.
        Included for interface completeness.
        """
        pass


# Global token store instance
token_store = RedisTokenStore()


def init_jwt_redis(app):
    """Initialize JWT token blacklist with Redis"""
    token_store.init_app(app)
    return token_store


def is_token_revoked(jwt_header: Dict[str, Any], jwt_payload: Dict[str, Any]) -> bool:
    """
    Callback for Flask-JWT-Extended to check if a token is revoked.

    Called automatically by @jwt_required() decorator.
    """
    jti = jwt_payload.get('jti')
    if not jti:
        return False

    return token_store.is_token_blacklisted(jti)


def revoke_token(jti: str, token_type: str = 'access'):
    """
    Revoke a JWT token by adding it to the blacklist.

    Args:
        jti: JWT ID from the token payload
        token_type: 'access' or 'refresh' (determines TTL)
    """
    if token_type == 'access':
        expires_in = int(current_app.config['JWT_ACCESS_TOKEN_EXPIRES'].total_seconds())
    else:
        expires_in = int(current_app.config['JWT_REFRESH_TOKEN_EXPIRES'].total_seconds())

    token_store.blacklist_token(jti, expires_in)


def log_token_event(event: str, user_id: int, token_jti: Optional[str] = None, **extra):
    """
    Log JWT token events for security auditing.

    Args:
        event: Event type (e.g., 'token_issued', 'token_revoked', 'token_refreshed')
        user_id: User ID associated with the token
        token_jti: JWT ID (if available)
        **extra: Additional context to log
    """
    log_data = {
        'event': event,
        'user_id': user_id,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        **extra
    }

    if token_jti:
        log_data['jti'] = token_jti

    logger.info(f'JWT Event: {event}', extra=log_data)

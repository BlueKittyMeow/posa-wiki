"""Application configuration classes."""
import os
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / '.env'
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv()

def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default

def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in ('true', '1', 'yes', 'on')

class Config:
    """Base configuration shared across environments."""

    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-change-me')
    DATABASE_PATH = os.getenv('DATABASE_PATH', str(BASE_DIR / 'posa_wiki.db'))

    # Pagination defaults
    VIDEOS_PER_PAGE = _int_env('VIDEOS_PER_PAGE', 24)
    PEOPLE_PER_PAGE = _int_env('PEOPLE_PER_PAGE', 20)
    DOGS_PER_PAGE = _int_env('DOGS_PER_PAGE', 20)
    SERIES_PER_PAGE = _int_env('SERIES_PER_PAGE', 20)
    TRIPS_PER_PAGE = _int_env('TRIPS_PER_PAGE', 20)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')

    WTF_CSRF_TIME_LIMIT = None
    WTF_CSRF_SSL_STRICT = False
    WTF_CSRF_CHECK_DEFAULT = True

    # Exempt API endpoints from CSRF (they use JWT tokens instead)
    WTF_CSRF_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE']  # GET is always exempt

    # JWT Configuration
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=_int_env('JWT_ACCESS_TOKEN_MINUTES', 15))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=_int_env('JWT_REFRESH_TOKEN_DAYS', 7))

    # JWT Cookie Settings (for web clients)
    JWT_TOKEN_LOCATION = ['cookies', 'headers']  # Support both cookie and header auth
    JWT_COOKIE_SECURE = False  # Override in production
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_COOKIE_SAMESITE = 'Lax'
    JWT_ACCESS_COOKIE_NAME = 'access_token'
    JWT_REFRESH_COOKIE_NAME = 'refresh_token'

    # Redis Configuration (for JWT blacklist and rate limiting)
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    REDIS_ENABLED = _bool_env('REDIS_ENABLED', False)  # Disabled by default in dev

    @staticmethod
    def init_app(app):
        """Hook for any environment-specific initialization."""
        return None

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False
    SESSION_COOKIE_SECURE = False
    SEND_FILE_MAX_AGE_DEFAULT = 0

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    SEND_FILE_MAX_AGE_DEFAULT = 31536000  # one year
    WTF_CSRF_TIME_LIMIT = 3600
    WTF_CSRF_SSL_STRICT = True

    # JWT Production Settings
    JWT_COOKIE_SECURE = True
    REDIS_ENABLED = True

    @staticmethod
    def init_app(app):
        Config.init_app(app)
        if app.config['SECRET_KEY'] == 'dev-secret-change-me':
            raise RuntimeError('Production requires FLASK_SECRET_KEY environment variable')
        if app.config['JWT_SECRET_KEY'] == app.config['SECRET_KEY']:
            app.logger.warning('JWT_SECRET_KEY not set, using FLASK_SECRET_KEY')

class TestingConfig(Config):
    DEBUG = False
    TESTING = True
    SESSION_COOKIE_SECURE = False
    SEND_FILE_MAX_AGE_DEFAULT = 0

CONFIG_BY_NAME = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
}

"""Application configuration classes."""
import os
from pathlib import Path

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

    @staticmethod
    def init_app(app):
        Config.init_app(app)
        if app.config['SECRET_KEY'] == 'dev-secret-change-me':
            raise RuntimeError('Production requires FLASK_SECRET_KEY environment variable')

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

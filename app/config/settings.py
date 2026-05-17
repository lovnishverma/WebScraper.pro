"""
Application configuration classes for different environments.
Uses environment variables with sensible defaults.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# app/config/settings.py -> parent (config) -> parent (app) -> parent (project root)
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class BaseConfig:
    """Base configuration shared across all environments."""

    # Flask
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production-32-chars!!")
    DEBUG: bool = False
    TESTING: bool = False

    # SQLAlchemy
    SQLALCHEMY_DATABASE_URI: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'database' / 'scraper.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # CSRF
    WTF_CSRF_ENABLED: bool = os.getenv("WTF_CSRF_ENABLED", "True") == "True"
    WTF_CSRF_TIME_LIMIT: int = 3600

    # Session
    SESSION_COOKIE_SECURE: bool = os.getenv("SESSION_COOKIE_SECURE", "False") == "True"
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    PERMANENT_SESSION_LIFETIME: int = 86400

    # Rate limiting
    RATELIMIT_DEFAULT: str = os.getenv("RATELIMIT_DEFAULT", "200 per hour")
    RATELIMIT_STORAGE_URL: str = os.getenv("RATELIMIT_STORAGE_URL", "memory://")
    RATELIMIT_HEADERS_ENABLED: bool = True

    # Scraping engine
    MAX_CONCURRENT_JOBS: int = int(os.getenv("MAX_CONCURRENT_JOBS", "5"))
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    DEFAULT_DELAY: float = float(os.getenv("DEFAULT_DELAY", "1.0"))
    MAX_PAGES: int = int(os.getenv("MAX_PAGES", "50"))

    # Directories
    EXPORT_DIR: Path = BASE_DIR / os.getenv("EXPORT_DIR", "exports")
    LOG_DIR: Path = BASE_DIR / os.getenv("LOG_DIR", "logs")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    @classmethod
    def init_app(cls, app) -> None:
        """Hook for environment-specific initialization."""
        # Ensure required directories exist
        cls.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOG_DIR.mkdir(parents=True, exist_ok=True)
        (BASE_DIR / "database").mkdir(parents=True, exist_ok=True)


class DevelopmentConfig(BaseConfig):
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    SESSION_COOKIE_SECURE: bool = False


class ProductionConfig(BaseConfig):
    DEBUG: bool = False
    SESSION_COOKIE_SECURE: bool = True
    LOG_LEVEL: str = "WARNING"
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 10,
        "max_overflow": 20,
    }


class TestingConfig(BaseConfig):
    TESTING: bool = True
    DEBUG: bool = True
    WTF_CSRF_ENABLED: bool = False
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}


def get_config() -> type:
    env = os.getenv("FLASK_ENV", "development").lower()
    return config_map.get(env, DevelopmentConfig)

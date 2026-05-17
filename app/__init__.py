"""
Application factory.
Create and configure the Flask app with all extensions, blueprints, and middleware.
"""
from __future__ import annotations

import logging

from flask import Flask
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app.config import get_config
from app.models import db
from app.middleware import register_middleware
from app.utils.logging_config import configure_logging

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)

logger = logging.getLogger(__name__)


def create_app(config_class=None) -> Flask:
    """Application factory — creates a fully configured Flask app."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # --- Load config ---
    cfg = config_class or get_config()
    app.config.from_object(cfg)
    cfg.init_app(app)

    # --- Logging ---
    configure_logging(
        log_level=app.config.get("LOG_LEVEL", "INFO"),
        log_dir=str(app.config.get("LOG_DIR", "logs")),
    )

    # --- Extensions ---
    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # --- Middleware ---
    register_middleware(app)

    # --- Blueprints ---
    from app.routes import main_bp, jobs_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(jobs_bp)

    # Apply rate limiting to API routes
    limiter.limit("60 per minute")(jobs_bp)

    # --- Database init ---
    with app.app_context():
        db.create_all()
        _seed_defaults()

    logger.info("WebScraper Platform started [%s]", app.config.get("FLASK_ENV", "development"))
    return app


def _seed_defaults() -> None:
    """Seed default app settings if not present."""
    from app.models import AppSetting
    defaults = [
        ("max_concurrent_jobs", "5", "Maximum parallel scrape jobs"),
        ("default_delay", "1.0", "Default seconds between requests"),
        ("default_timeout", "30", "Default HTTP timeout in seconds"),
    ]
    for key, value, desc in defaults:
        if not AppSetting.query.filter_by(key=key).first():
            db.session.add(AppSetting(key=key, value=value, description=desc))
    db.session.commit()

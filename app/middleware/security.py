"""
Flask middleware:
- Request timing
- Security headers (XSS, clickjacking, content-type sniffing)
- Global error handlers (404, 429, 500)
"""
from __future__ import annotations

import logging
import time

from flask import Flask, jsonify, request, render_template

logger = logging.getLogger(__name__)


def register_middleware(app: Flask) -> None:
    """Register all middleware and error handlers on the Flask app."""

    @app.before_request
    def start_timer() -> None:
        request._start_time = time.monotonic()

    @app.after_request
    def add_security_headers(response):
        duration = time.monotonic() - getattr(request, "_start_time", time.monotonic())
        response.headers["X-Response-Time"] = f"{duration * 1000:.2f}ms"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        logger.debug(
            "%s %s -> %d (%.2fms)",
            request.method,
            request.path,
            response.status_code,
            duration * 1000,
        )
        return response

    @app.errorhandler(400)
    def bad_request(exc):
        if request.is_json:
            return jsonify({"error": "Bad request", "detail": str(exc)}), 400
        return render_template("pages/error.html", code=400, message="Bad Request"), 400

    @app.errorhandler(404)
    def not_found(exc):
        if request.is_json:
            return jsonify({"error": "Not found"}), 404
        return render_template("pages/error.html", code=404, message="Page Not Found"), 404

    @app.errorhandler(429)
    def rate_limited(exc):
        if request.is_json:
            return jsonify({"error": "Rate limit exceeded. Please slow down."}), 429
        return render_template("pages/error.html", code=429, message="Rate limit exceeded"), 429

    @app.errorhandler(500)
    def internal_error(exc):
        logger.exception("Internal server error: %s", exc)
        if request.is_json:
            return jsonify({"error": "Internal server error"}), 500
        return render_template("pages/error.html", code=500, message="Internal Server Error"), 500

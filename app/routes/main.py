"""
Dashboard and main UI routes.
Blueprint: 'main' — prefix: /
"""
from __future__ import annotations

import logging

from flask import Blueprint, render_template, jsonify

from app.services import get_dashboard_stats

logger = logging.getLogger(__name__)

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    stats = get_dashboard_stats()
    return render_template("pages/dashboard.html", stats=stats)


@main_bp.route("/health")
def health():
    """Health check endpoint for load balancers and monitoring."""
    return jsonify({"status": "ok", "service": "WebScraper Platform"}), 200


@main_bp.route("/metrics")
def metrics():
    """Simple performance metrics endpoint."""
    stats = get_dashboard_stats()
    return jsonify(stats), 200

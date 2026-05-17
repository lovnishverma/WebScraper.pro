"""
Scrape job routes (UI + REST API).
Blueprint: 'jobs' — prefix: /jobs
"""
from __future__ import annotations

import logging
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from app.services import (
    create_job,
    cancel_job,
    delete_job,
    execute_job_async,
    get_job,
    get_job_logs,
    get_job_results,
    list_jobs,
    export_json,
    export_csv,
    export_excel,
    get_job_exports,
)
from app.utils.validators import validate_job_data, sanitize_string

logger = logging.getLogger(__name__)

jobs_bp = Blueprint("jobs", __name__, url_prefix="/jobs")


# ---------------------------------------------------------------------------
# UI Routes
# ---------------------------------------------------------------------------


@jobs_bp.route("/")
def list_view():
    page = request.args.get("page", 1, type=int)
    status = request.args.get("status")
    search = request.args.get("search")
    pagination = list_jobs(page=page, per_page=20, status=status, search=search)
    return render_template(
        "pages/jobs.html",
        pagination=pagination,
        status_filter=status,
        search=search,
    )


@jobs_bp.route("/new", methods=["GET", "POST"])
def new_job():
    if request.method == "POST":
        data = {k: v for k, v in request.form.items()}
        # Sanitize string fields
        for field in ("name", "html_tag", "css_selector", "xpath_selector", "attribute_name", "user_agent"):
            if field in data:
                data[field] = sanitize_string(data[field])

        # Checkboxes
        data["follow_pagination"] = "follow_pagination" in request.form
        data["infinite_scroll"] = "infinite_scroll" in request.form
        data["download_images"] = "download_images" in request.form
        data["check_robots_txt"] = "check_robots_txt" in request.form
        data["deduplicate"] = "deduplicate" in request.form

        valid, errors = validate_job_data(data)
        if not valid:
            return render_template("pages/new_job.html", errors=errors, form_data=data)

        job = create_job(data)
        execute_job_async(job.id, current_app._get_current_object())
        flash(f"Job #{job.id} started successfully!", "success")
        return redirect(url_for("jobs.detail", job_id=job.id))

    return render_template("pages/new_job.html", errors={}, form_data={})


@jobs_bp.route("/<int:job_id>")
def detail(job_id: int):
    job = get_job(job_id)
    if not job:
        abort(404)
    results_page = get_job_results(job_id, page=request.args.get("rpage", 1, type=int), per_page=50)
    logs_page = get_job_logs(job_id, page=1, per_page=200)
    exports = get_job_exports(job_id)
    return render_template(
        "pages/job_detail.html",
        job=job,
        results=results_page,
        logs=logs_page,
        exports=exports,
    )


@jobs_bp.route("/<int:job_id>/delete", methods=["POST"])
def delete(job_id: int):
    if not delete_job(job_id):
        abort(404)
    flash(f"Job #{job_id} deleted.", "info")
    return redirect(url_for("jobs.list_view"))


@jobs_bp.route("/<int:job_id>/cancel", methods=["POST"])
def cancel(job_id: int):
    if not cancel_job(job_id):
        flash("Cannot cancel this job.", "warning")
    else:
        flash(f"Job #{job_id} cancelled.", "info")
    return redirect(url_for("jobs.detail", job_id=job_id))


@jobs_bp.route("/<int:job_id>/rerun", methods=["POST"])
def rerun(job_id: int):
    job = get_job(job_id)
    if not job:
        abort(404)
    job.status = "pending"
    from app.models import db
    db.session.commit()
    execute_job_async(job_id, current_app._get_current_object())
    flash(f"Job #{job_id} queued for re-run.", "success")
    return redirect(url_for("jobs.detail", job_id=job_id))


# ---------------------------------------------------------------------------
# Export Routes
# ---------------------------------------------------------------------------


@jobs_bp.route("/<int:job_id>/export/<string:fmt>")
def export(job_id: int, fmt: str):
    job = get_job(job_id)
    if not job:
        abort(404)

    exporters = {"json": export_json, "csv": export_csv, "excel": export_excel}
    if fmt not in exporters:
        abort(400)

    filepath = exporters[fmt](job_id)
    if not filepath or not Path(filepath).exists():
        flash("Export failed. No results to export.", "danger")
        return redirect(url_for("jobs.detail", job_id=job_id))

    mime_map = {
        "json": "application/json",
        "csv": "text/csv",
        "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return send_file(filepath, mimetype=mime_map[fmt], as_attachment=True)


# ---------------------------------------------------------------------------
# REST API Routes
# ---------------------------------------------------------------------------


@jobs_bp.route("/api/jobs", methods=["GET"])
def api_list():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    status = request.args.get("status")
    search = request.args.get("search")
    pagination = list_jobs(page=page, per_page=per_page, status=status, search=search)
    return jsonify(
        {
            "jobs": [j.to_dict() for j in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "pages": pagination.pages,
            "per_page": pagination.per_page,
        }
    )


@jobs_bp.route("/api/jobs", methods=["POST"])
def api_create():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    valid, errors = validate_job_data(data)
    if not valid:
        return jsonify({"error": "Validation failed", "details": errors}), 422

    job = create_job(data)
    execute_job_async(job.id, current_app._get_current_object())
    return jsonify({"job": job.to_dict(), "message": "Job created and queued"}), 201


@jobs_bp.route("/api/jobs/<int:job_id>", methods=["GET"])
def api_get(job_id: int):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"job": job.to_dict()})


@jobs_bp.route("/api/jobs/<int:job_id>", methods=["DELETE"])
def api_delete(job_id: int):
    if not delete_job(job_id):
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"message": f"Job {job_id} deleted"}), 200


@jobs_bp.route("/api/jobs/<int:job_id>/results", methods=["GET"])
def api_results(job_id: int):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 500)
    pagination = get_job_results(job_id, page=page, per_page=per_page)
    return jsonify(
        {
            "results": [r.to_dict() for r in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "pages": pagination.pages,
        }
    )


@jobs_bp.route("/api/jobs/<int:job_id>/logs", methods=["GET"])
def api_logs(job_id: int):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    page = request.args.get("page", 1, type=int)
    pagination = get_job_logs(job_id, page=page, per_page=100)
    return jsonify(
        {
            "logs": [l.to_dict() for l in pagination.items],
            "total": pagination.total,
        }
    )


@jobs_bp.route("/api/jobs/<int:job_id>/status", methods=["GET"])
def api_status(job_id: int):
    """Lightweight polling endpoint for live status updates."""
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(
        {
            "status": job.status,
            "total_items": job.total_items,
            "pages_scraped": job.pages_scraped,
            "error_count": job.error_count,
        }
    )

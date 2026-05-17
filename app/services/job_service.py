"""
Service layer for scrape job management.
Handles job creation, execution, status updates, and result persistence.
Keeps routes thin and business logic centralized here.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from app.models import db, ScrapeJob, ScrapeResult, JobLog, ExportRecord
from app.scrapers.engine import ScrapeRequest, run_scrape, ScrapedItem

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Job CRUD
# ---------------------------------------------------------------------------


def create_job(data: dict, user_id: Optional[int] = None) -> ScrapeJob:
    """Create and persist a new ScrapeJob from validated form/API data."""
    custom_headers = data.get("custom_headers") or {}
    if isinstance(custom_headers, str):
        try:
            custom_headers = json.loads(custom_headers)
        except json.JSONDecodeError:
            custom_headers = {}

    job = ScrapeJob(
        user_id=user_id,
        name=data.get("name", f"Job - {data['url'][:50]}"),
        url=data["url"],
        html_tag=data.get("html_tag") or None,
        css_selector=data.get("css_selector") or None,
        xpath_selector=data.get("xpath_selector") or None,
        attribute_name=data.get("attribute_name") or None,
        extraction_type=data.get("extraction_type", "text"),
        scrape_type=data.get("scrape_type", "static"),
        follow_pagination=bool(data.get("follow_pagination", False)),
        max_pages=int(data.get("max_pages", 1)),
        infinite_scroll=bool(data.get("infinite_scroll", False)),
        scroll_count=int(data.get("scroll_count", 3)),
        download_images=bool(data.get("download_images", False)),
        custom_headers=json.dumps(custom_headers),
        user_agent=data.get("user_agent") or None,
        delay_seconds=float(data.get("delay_seconds", 1.0)),
        timeout_seconds=int(data.get("timeout_seconds", 30)),
        max_retries=int(data.get("max_retries", 3)),
        check_robots_txt=bool(data.get("check_robots_txt", True)),
        deduplicate=bool(data.get("deduplicate", True)),
        status="pending",
    )
    db.session.add(job)
    db.session.commit()
    _add_log(job.id, "INFO", f"Job created: {job.name}")
    return job


def get_job(job_id: int) -> Optional[ScrapeJob]:
    return ScrapeJob.query.get(job_id)


def list_jobs(
    page: int = 1,
    per_page: int = 20,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> Any:
    q = ScrapeJob.query.order_by(ScrapeJob.created_at.desc())
    if status:
        q = q.filter(ScrapeJob.status == status)
    if search:
        q = q.filter(
            ScrapeJob.name.ilike(f"%{search}%") | ScrapeJob.url.ilike(f"%{search}%")
        )
    return q.paginate(page=page, per_page=per_page, error_out=False)


def delete_job(job_id: int) -> bool:
    job = ScrapeJob.query.get(job_id)
    if not job:
        return False
    db.session.delete(job)
    db.session.commit()
    return True


def cancel_job(job_id: int) -> bool:
    job = ScrapeJob.query.get(job_id)
    if not job or job.status not in ("pending", "running"):
        return False
    job.status = "cancelled"
    db.session.commit()
    _add_log(job_id, "WARNING", "Job cancelled by user")
    return True


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def execute_job(job_id: int, app=None) -> None:
    """
    Execute a scrape job synchronously.
    Designed to be called in a background thread with app context.
    """
    if app:
        with app.app_context():
            _run_job(job_id)
    else:
        _run_job(job_id)


def execute_job_async(job_id: int, app) -> threading.Thread:
    """Spawn a daemon thread for async job execution."""
    thread = threading.Thread(target=execute_job, args=(job_id, app), daemon=True)
    thread.start()
    return thread


def _run_job(job_id: int) -> None:
    job = ScrapeJob.query.get(job_id)
    if not job:
        logger.error("Job %s not found", job_id)
        return

    job.status = "running"
    job.started_at = utcnow()
    db.session.commit()

    _add_log(job_id, "INFO", f"Starting scrape: {job.url}")

    try:
        req = ScrapeRequest(
            url=job.url,
            html_tag=job.html_tag,
            css_selector=job.css_selector,
            xpath_selector=job.xpath_selector,
            attribute_name=job.attribute_name,
            extraction_type=job.extraction_type,
            scrape_type=job.scrape_type,
            follow_pagination=job.follow_pagination,
            max_pages=job.max_pages,
            infinite_scroll=job.infinite_scroll,
            scroll_count=job.scroll_count,
            download_images=job.download_images,
            custom_headers=job.custom_headers_dict,
            user_agent=job.user_agent,
            delay_seconds=job.delay_seconds,
            timeout_seconds=job.timeout_seconds,
            max_retries=job.max_retries,
            check_robots_txt=job.check_robots_txt,
            deduplicate=job.deduplicate,
        )

        response = run_scrape(req)

        # Persist results
        _save_results(job_id, response.items)

        # Log errors
        for err in response.errors:
            _add_log(job_id, "ERROR", err)

        job.status = "completed" if response.error_count == 0 else "failed"
        job.total_items = len(response.items)
        job.pages_scraped = response.pages_scraped
        job.error_count = response.error_count
        job.duration_seconds = response.duration_seconds
        job.completed_at = utcnow()
        db.session.commit()

        _add_log(
            job_id,
            "INFO",
            f"Completed: {len(response.items)} items from {response.pages_scraped} pages "
            f"in {response.duration_seconds:.2f}s",
        )

    except Exception as exc:
        logger.exception("Job %s failed with unexpected error", job_id)
        job.status = "failed"
        job.error_count = (job.error_count or 0) + 1
        job.completed_at = utcnow()
        db.session.commit()
        _add_log(job_id, "ERROR", f"Fatal error: {type(exc).__name__}: {exc}")


def _save_results(job_id: int, items: list[ScrapedItem]) -> None:
    """Bulk insert scraped results."""
    if not items:
        return
    objs = [
        ScrapeResult(
            job_id=job_id,
            page_url=item.page_url,
            page_num=item.page_num,
            item_index=item.item_index,
            content=item.content,
            content_type=item.content_type,
            content_hash=item.content_hash,
            metadata_=json.dumps(item.metadata) if item.metadata else None,
        )
        for item in items
    ]
    db.session.bulk_save_objects(objs)
    db.session.commit()


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


def _add_log(job_id: int, level: str, message: str, details: Optional[dict] = None) -> None:
    try:
        log = JobLog(
            job_id=job_id,
            level=level,
            message=message,
            details=json.dumps(details) if details else None,
        )
        db.session.add(log)
        db.session.commit()
    except Exception as exc:
        logger.warning("Could not persist log for job %s: %s", job_id, exc)


def get_job_logs(job_id: int, page: int = 1, per_page: int = 100) -> Any:
    return (
        JobLog.query.filter_by(job_id=job_id)
        .order_by(JobLog.created_at.asc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )


def get_job_results(job_id: int, page: int = 1, per_page: int = 50) -> Any:
    return (
        ScrapeResult.query.filter_by(job_id=job_id)
        .order_by(ScrapeResult.page_num, ScrapeResult.item_index)
        .paginate(page=page, per_page=per_page, error_out=False)
    )


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------


def get_dashboard_stats() -> dict:
    total = ScrapeJob.query.count()
    completed = ScrapeJob.query.filter_by(status="completed").count()
    failed = ScrapeJob.query.filter_by(status="failed").count()
    running = ScrapeJob.query.filter_by(status="running").count()
    pending = ScrapeJob.query.filter_by(status="pending").count()
    total_items = db.session.query(db.func.sum(ScrapeJob.total_items)).scalar() or 0

    recent_jobs = (
        ScrapeJob.query.order_by(ScrapeJob.created_at.desc()).limit(5).all()
    )

    return {
        "total_jobs": total,
        "completed_jobs": completed,
        "failed_jobs": failed,
        "running_jobs": running,
        "pending_jobs": pending,
        "total_items_scraped": total_items,
        "recent_jobs": [j.to_dict() for j in recent_jobs],
        "success_rate": round((completed / total * 100) if total else 0, 1),
    }

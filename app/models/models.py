"""
SQLAlchemy ORM models with relationships, indexes, and cascading deletes.
All timestamps are UTC. All text fields are sanitized at the service layer.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Enum,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

db = SQLAlchemy()


class BaseModel(db.Model):
    """Base model with __allow_unmapped__ for legacy annotations."""
    __abstract__ = True
    __allow_unmapped__ = True


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Enumerations (stored as VARCHAR for SQLite compatibility)
# ---------------------------------------------------------------------------

JOB_STATUS = ("pending", "running", "completed", "failed", "cancelled")
SCRAPE_TYPE = ("static", "dynamic")
EXTRACTION_TYPE = ("text", "images", "links", "attributes", "table", "json_ld", "full_html")
EXPORT_FORMAT = ("json", "csv", "excel")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class User(BaseModel):
    """Simple user model — single-user by default, extendable to multi-user."""

    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True)
    username: str = Column(String(80), unique=True, nullable=False, index=True)
    email: str = Column(String(120), unique=True, nullable=False, index=True)
    password_hash: str = Column(String(256), nullable=False)
    is_active: bool = Column(Boolean, default=True, nullable=False)
    is_admin: bool = Column(Boolean, default=False, nullable=False)
    api_key: Optional[str] = Column(String(64), unique=True, index=True)
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)
    updated_at: datetime = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    jobs: list[ScrapeJob] = relationship(
        "ScrapeJob", back_populates="user", cascade="all, delete-orphan", lazy="select"
    )
    schedules: list[Schedule] = relationship(
        "Schedule", back_populates="user", cascade="all, delete-orphan", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<User {self.username}>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "is_active": self.is_active,
            "is_admin": self.is_admin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ScrapeJob(BaseModel):
    """Represents a single scraping job with all configuration."""

    __tablename__ = "scrape_jobs"
    __table_args__ = (
        Index("ix_scrape_jobs_status", "status"),
        Index("ix_scrape_jobs_created_at", "created_at"),
        Index("ix_scrape_jobs_user_id", "user_id"),
    )

    id: int = Column(Integer, primary_key=True)
    user_id: Optional[int] = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name: str = Column(String(200), nullable=False)
    url: str = Column(Text, nullable=False)

    # Selectors
    html_tag: Optional[str] = Column(String(100))
    css_selector: Optional[str] = Column(Text)
    xpath_selector: Optional[str] = Column(Text)
    attribute_name: Optional[str] = Column(String(100))

    # Configuration
    extraction_type: str = Column(
        Enum(*EXTRACTION_TYPE, name="extraction_type"), default="text", nullable=False
    )
    scrape_type: str = Column(
        Enum(*SCRAPE_TYPE, name="scrape_type"), default="static", nullable=False
    )
    status: str = Column(
        Enum(*JOB_STATUS, name="job_status"), default="pending", nullable=False
    )

    # Advanced options
    follow_pagination: bool = Column(Boolean, default=False)
    max_pages: int = Column(Integer, default=1)
    infinite_scroll: bool = Column(Boolean, default=False)
    scroll_count: int = Column(Integer, default=3)
    download_images: bool = Column(Boolean, default=False)
    custom_headers: Optional[str] = Column(Text)  # JSON string
    user_agent: Optional[str] = Column(Text)
    delay_seconds: float = Column(Float, default=1.0)
    timeout_seconds: int = Column(Integer, default=30)
    max_retries: int = Column(Integer, default=3)
    check_robots_txt: bool = Column(Boolean, default=True)
    deduplicate: bool = Column(Boolean, default=True)

    # Stats
    total_items: int = Column(Integer, default=0)
    pages_scraped: int = Column(Integer, default=0)
    error_count: int = Column(Integer, default=0)
    duration_seconds: Optional[float] = Column(Float)

    # Timestamps
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)
    updated_at: datetime = Column(DateTime, default=utcnow, onupdate=utcnow)
    started_at: Optional[datetime] = Column(DateTime)
    completed_at: Optional[datetime] = Column(DateTime)

    # Relationships
    user: Optional[User] = relationship("User", back_populates="jobs")
    results: list[ScrapeResult] = relationship(
        "ScrapeResult", back_populates="job", cascade="all, delete-orphan", lazy="select"
    )
    logs: list[JobLog] = relationship(
        "JobLog", back_populates="job", cascade="all, delete-orphan", lazy="select"
    )
    exports: list[ExportRecord] = relationship(
        "ExportRecord", back_populates="job", cascade="all, delete-orphan", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<ScrapeJob {self.id} [{self.status}] {self.url[:50]}>"

    @property
    def custom_headers_dict(self) -> dict:
        if self.custom_headers:
            try:
                return json.loads(self.custom_headers)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "html_tag": self.html_tag,
            "css_selector": self.css_selector,
            "xpath_selector": self.xpath_selector,
            "extraction_type": self.extraction_type,
            "scrape_type": self.scrape_type,
            "status": self.status,
            "follow_pagination": self.follow_pagination,
            "max_pages": self.max_pages,
            "infinite_scroll": self.infinite_scroll,
            "total_items": self.total_items,
            "pages_scraped": self.pages_scraped,
            "error_count": self.error_count,
            "duration_seconds": self.duration_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class ScrapeResult(BaseModel):
    """Individual scraped data item linked to a job."""

    __tablename__ = "scrape_results"
    __table_args__ = (
        Index("ix_scrape_results_job_id", "job_id"),
        Index("ix_scrape_results_page_num", "page_num"),
        Index("ix_scrape_results_content_hash", "content_hash"),
    )

    id: int = Column(Integer, primary_key=True)
    job_id: int = Column(Integer, ForeignKey("scrape_jobs.id", ondelete="CASCADE"), nullable=False)
    page_url: str = Column(Text, nullable=False)
    page_num: int = Column(Integer, default=1, nullable=False)
    item_index: int = Column(Integer, default=0)
    content: Optional[str] = Column(Text)
    content_type: str = Column(String(50), default="text")
    content_hash: Optional[str] = Column(String(64))
    metadata_: Optional[str] = Column("metadata", Text)  # JSON
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)

    # Relationship
    job: ScrapeJob = relationship("ScrapeJob", back_populates="results")

    def __repr__(self) -> str:
        return f"<ScrapeResult job={self.job_id} page={self.page_num} idx={self.item_index}>"

    @property
    def metadata_dict(self) -> dict:
        if self.metadata_:
            try:
                return json.loads(self.metadata_)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "page_url": self.page_url,
            "page_num": self.page_num,
            "item_index": self.item_index,
            "content": self.content,
            "content_type": self.content_type,
            "metadata": self.metadata_dict,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class JobLog(BaseModel):
    """Structured logs for each scraping job."""

    __tablename__ = "job_logs"
    __table_args__ = (
        Index("ix_job_logs_job_id", "job_id"),
        Index("ix_job_logs_level", "level"),
        Index("ix_job_logs_created_at", "created_at"),
    )

    id: int = Column(Integer, primary_key=True)
    job_id: int = Column(Integer, ForeignKey("scrape_jobs.id", ondelete="CASCADE"), nullable=False)
    level: str = Column(String(10), default="INFO", nullable=False)
    message: str = Column(Text, nullable=False)
    details: Optional[str] = Column(Text)  # JSON for structured extras
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)

    job: ScrapeJob = relationship("ScrapeJob", back_populates="logs")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "level": self.level,
            "message": self.message,
            "details": self.details,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ExportRecord(BaseModel):
    """Tracks export files generated for each job."""

    __tablename__ = "export_records"
    __table_args__ = (Index("ix_export_records_job_id", "job_id"),)

    id: int = Column(Integer, primary_key=True)
    job_id: int = Column(Integer, ForeignKey("scrape_jobs.id", ondelete="CASCADE"), nullable=False)
    format: str = Column(Enum(*EXPORT_FORMAT, name="export_format"), nullable=False)
    filename: str = Column(String(255), nullable=False)
    filepath: str = Column(Text, nullable=False)
    file_size_bytes: Optional[int] = Column(Integer)
    row_count: int = Column(Integer, default=0)
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)

    job: ScrapeJob = relationship("ScrapeJob", back_populates="exports")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "format": self.format,
            "filename": self.filename,
            "file_size_bytes": self.file_size_bytes,
            "row_count": self.row_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Schedule(BaseModel):
    """APScheduler-backed recurring scrape schedules."""

    __tablename__ = "schedules"
    __table_args__ = (Index("ix_schedules_user_id", "user_id"),)

    id: int = Column(Integer, primary_key=True)
    user_id: Optional[int] = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name: str = Column(String(200), nullable=False)
    cron_expression: str = Column(String(100), nullable=False)  # e.g. "0 9 * * 1"
    job_config: str = Column(Text, nullable=False)  # JSON of ScrapeJob config
    is_active: bool = Column(Boolean, default=True, nullable=False)
    last_run_at: Optional[datetime] = Column(DateTime)
    next_run_at: Optional[datetime] = Column(DateTime)
    run_count: int = Column(Integer, default=0)
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)
    updated_at: datetime = Column(DateTime, default=utcnow, onupdate=utcnow)

    user: Optional[User] = relationship("User", back_populates="schedules")

    @property
    def job_config_dict(self) -> dict:
        try:
            return json.loads(self.job_config)
        except (json.JSONDecodeError, TypeError):
            return {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "cron_expression": self.cron_expression,
            "is_active": self.is_active,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "run_count": self.run_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AppSetting(BaseModel):
    """Key-value application settings stored in the DB."""

    __tablename__ = "app_settings"

    id: int = Column(Integer, primary_key=True)
    key: str = Column(String(100), unique=True, nullable=False, index=True)
    value: str = Column(Text, nullable=False)
    description: Optional[str] = Column(Text)
    updated_at: datetime = Column(DateTime, default=utcnow, onupdate=utcnow)

    @classmethod
    def get(cls, key: str, default: str = "") -> str:
        row = cls.query.filter_by(key=key).first()
        return row.value if row else default

    @classmethod
    def set(cls, key: str, value: str, description: str = "") -> None:
        row = cls.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            row = cls(key=key, value=value, description=description)
            db.session.add(row)
        db.session.commit()

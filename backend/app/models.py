"""SQLModel table definitions: persisted jobs and singleton app settings."""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, enum.Enum):
    queued = "queued"
    downloading = "downloading"
    post_processing = "post-processing"
    completed = "completed"
    error = "error"
    cancelled = "cancelled"


# Terminal states no longer occupy a worker / cannot be cancelled.
TERMINAL_STATES = {JobStatus.completed, JobStatus.error, JobStatus.cancelled}


class Job(SQLModel, table=True):
    """A single download request and its lifecycle state."""

    id: int | None = Field(default=None, primary_key=True)

    url: str
    status: JobStatus = Field(default=JobStatus.queued, index=True)

    # Requested options (snapshot so re-download / history is reproducible).
    format_id: str | None = None
    quality_preset: str | None = None
    audio_only: bool = False
    subtitles: bool = False
    embed_thumbnail: bool = False
    sponsorblock: bool = False
    output_template: str | None = None

    # Full DownloadOptions snapshot (see options.py) as JSON. Canonical store for
    # every newer knob so adding a feature needs no per-column migration.
    options: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    # Metadata captured from yt-dlp (best-effort).
    title: str | None = None
    uploader: str | None = None
    duration: float | None = None
    thumbnail: str | None = None
    ext: str | None = None

    # Progress / result.
    progress: float = 0.0  # 0..100
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed: float | None = None
    eta: int | None = None
    filepath: str | None = None  # absolute path of finished file
    filesize: int | None = None
    error_message: str | None = None

    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None


class AppSettings(SQLModel, table=True):
    """Singleton row (id=1) holding user-configurable runtime settings."""

    id: int | None = Field(default=1, primary_key=True)
    download_dir: str
    default_format: str = "best"  # preset key: best | 1080p | 720p | audio
    max_concurrency: int = 2
    default_output_template: str = "%(title)s [%(id)s].%(ext)s"
    naming: str = "%(title)s [%(id)s].%(ext)s"  # alias kept for clarity in UI

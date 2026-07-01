"""Pydantic request/response models — the API contract shared with the frontend.

Field names here are the source of truth for the hand-written TypeScript client.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .models import JobStatus
from .options import DownloadOptions


# ---------- Probe ----------
class ProbeRequest(BaseModel):
    url: str


class FormatInfo(BaseModel):
    format_id: str
    ext: str | None = None
    resolution: str | None = None
    fps: float | None = None
    vcodec: str | None = None
    acodec: str | None = None
    filesize: int | None = None
    format_note: str | None = None
    audio_only: bool = False
    video_only: bool = False


class ProbeResponse(BaseModel):
    url: str
    title: str | None = None
    uploader: str | None = None
    duration: float | None = None
    thumbnail: str | None = None
    is_playlist: bool = False
    playlist_count: int | None = None
    formats: list[FormatInfo] = []


# ---------- Downloads ----------
class DownloadRequest(BaseModel):
    url: str
    format_id: str | None = None
    quality_preset: str | None = None  # best | 1080p | 720p | audio
    audio_only: bool = False
    subtitles: bool = False
    embed_thumbnail: bool = False
    sponsorblock: bool = False
    output_template: str | None = None
    # Full set of newer knobs. Legacy top-level fields above stay for back-compat.
    options: DownloadOptions | None = None


class JobRead(BaseModel):
    id: int
    url: str
    status: JobStatus
    format_id: str | None = None
    quality_preset: str | None = None
    audio_only: bool
    subtitles: bool
    embed_thumbnail: bool
    sponsorblock: bool
    output_template: str | None = None
    options: dict = {}

    title: str | None = None
    uploader: str | None = None
    duration: float | None = None
    thumbnail: str | None = None
    ext: str | None = None

    progress: float
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed: float | None = None
    eta: int | None = None
    filepath: str | None = None
    filesize: int | None = None
    error_message: str | None = None

    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class JobList(BaseModel):
    items: list[JobRead]
    total: int
    page: int
    page_size: int


class DeleteJobRequest(BaseModel):
    delete_file: bool = False


# ---------- Settings ----------
class SettingsRead(BaseModel):
    download_dir: str
    default_format: str
    max_concurrency: int
    default_output_template: str
    naming: str

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    download_dir: str | None = None
    default_format: str | None = None
    max_concurrency: int | None = None
    default_output_template: str | None = None
    naming: str | None = None


# ---------- Misc ----------
class CreatedJob(BaseModel):
    id: int


class HealthResponse(BaseModel):
    status: str
    ffmpeg: bool
    ffmpeg_version: str | None = None

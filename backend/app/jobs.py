"""Shared job-construction logic used by both the REST API and the Telegram bot.

Kept separate from routers/downloads.py so the two entry points can never drift:
probing, defaults, and the scheduled/queued split live here exactly once.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlmodel import Session

from .db import get_settings
from .downloader import ProbeError, probe
from .models import Job, JobStatus, utcnow
from .options import DownloadOptions


async def build_job(
    session: Session,
    url: str,
    *,
    format_id: str | None = None,
    quality_preset: str | None = None,
    audio_only: bool = False,
    subtitles: bool = False,
    embed_thumbnail: bool = False,
    sponsorblock: bool = False,
    output_template: str | None = None,
    options: DownloadOptions | None = None,
    scheduled_at: datetime | None = None,
) -> Job:
    """Construct, best-effort probe-enrich, and persist a Job.

    Returns the committed Job. Caller is responsible for enqueueing it via
    `manager.enqueue(job.id)` when `job.status != JobStatus.scheduled`.
    """
    settings = get_settings(session)
    sched = scheduled_at
    if sched is not None and sched.tzinfo is None:
        sched = sched.replace(tzinfo=timezone.utc)  # treat naive input as UTC
    is_scheduled = sched is not None and sched > utcnow()

    job = Job(
        url=url,
        status=JobStatus.scheduled if is_scheduled else JobStatus.queued,
        format_id=format_id,
        quality_preset=quality_preset,
        audio_only=audio_only,
        subtitles=subtitles,
        embed_thumbnail=embed_thumbnail,
        sponsorblock=sponsorblock,
        output_template=output_template or settings.default_output_template,
        options=options.model_dump(exclude_none=True) if options else {},
        scheduled_at=sched if is_scheduled else None,
    )

    # Best-effort metadata so the UI/history has a title immediately.
    try:
        info = await asyncio.to_thread(probe, url)
        if not info.is_playlist:
            job.title = info.title
            job.uploader = info.uploader
            job.duration = info.duration
            job.thumbnail = info.thumbnail
    except ProbeError:
        pass  # metadata is optional; the download attempt will surface real errors

    session.add(job)
    session.commit()
    session.refresh(job)
    return job

"""Download job endpoints: create, list, detail, cancel, delete."""
from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, func, select

from ..db import get_session, get_settings
from ..downloader import ProbeError, probe
from ..models import TERMINAL_STATES, Job, JobStatus
from ..options import redact
from ..queue import manager
from ..schemas import CreatedJob, DeleteJobRequest, DownloadRequest, JobList, JobRead

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


def _job_read(job: Job) -> JobRead:
    """Validate a Job into its API shape with secret option values masked."""
    read = JobRead.model_validate(job)
    read.options = redact(read.options)
    return read


@router.post("", response_model=CreatedJob, status_code=201)
async def create_download(req: DownloadRequest, session: Session = Depends(get_session)) -> CreatedJob:
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=422, detail="URL is required.")

    settings = get_settings(session)
    job = Job(
        url=url,
        status=JobStatus.queued,
        format_id=req.format_id,
        quality_preset=req.quality_preset,
        audio_only=req.audio_only,
        subtitles=req.subtitles,
        embed_thumbnail=req.embed_thumbnail,
        sponsorblock=req.sponsorblock,
        output_template=req.output_template or settings.default_output_template,
        options=req.options.model_dump(exclude_none=True) if req.options else {},
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

    await manager.enqueue(job.id)
    return CreatedJob(id=job.id)


@router.get("", response_model=JobList)
def list_downloads(
    session: Session = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: JobStatus | None = None,
) -> JobList:
    stmt = select(Job)
    count_stmt = select(func.count()).select_from(Job)
    if status is not None:
        stmt = stmt.where(Job.status == status)
        count_stmt = count_stmt.where(Job.status == status)
    total = session.exec(count_stmt).one()
    items = session.exec(
        stmt.order_by(Job.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return JobList(
        items=[_job_read(j) for j in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{job_id}", response_model=JobRead)
def get_download(job_id: int, session: Session = Depends(get_session)) -> JobRead:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _job_read(job)


@router.post("/{job_id}/cancel", response_model=JobRead)
def cancel_download(job_id: int, session: Session = Depends(get_session)) -> JobRead:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status in TERMINAL_STATES:
        raise HTTPException(status_code=409, detail=f"Job already {job.status.value}.")
    manager.cancel(job_id)
    session.refresh(job)
    return _job_read(job)


@router.delete("/{job_id}", status_code=204)
def delete_download(
    job_id: int,
    body: DeleteJobRequest | None = None,
    session: Session = Depends(get_session),
) -> None:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status not in TERMINAL_STATES:
        manager.cancel(job_id)
    if body and body.delete_file and job.filepath and os.path.exists(job.filepath):
        try:
            os.remove(job.filepath)
        except OSError:
            pass
    session.delete(job)
    session.commit()

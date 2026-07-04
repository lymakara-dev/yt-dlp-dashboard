"""Download job endpoints: create, list, detail, cancel, delete."""
from __future__ import annotations

import asyncio
import os
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, func, select

from ..db import get_session, get_settings
from ..downloader import ProbeError, probe
from ..models import TERMINAL_STATES, Job, JobStatus, utcnow
from ..options import redact
from ..queue import manager
from ..schemas import (
    BatchRequest,
    BulkCancelRequest,
    BulkCancelResult,
    CreatedBatch,
    CreatedJob,
    DeleteJobRequest,
    DownloadRequest,
    JobList,
    JobRead,
    ReorderRequest,
)

router = APIRouter(prefix="/api/downloads", tags=["downloads"])

# Non-terminal states shown on the Queue page, in worker-claim order.
_ACTIVE_STATES = [
    JobStatus.scheduled,
    JobStatus.queued,
    JobStatus.downloading,
    JobStatus.post_processing,
]


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
    # A future scheduled_at holds the job until the automation loop makes it due.
    sched = req.scheduled_at
    if sched is not None and sched.tzinfo is None:
        sched = sched.replace(tzinfo=timezone.utc)  # treat naive input as UTC
    is_scheduled = sched is not None and sched > utcnow()
    job = Job(
        url=url,
        status=JobStatus.scheduled if is_scheduled else JobStatus.queued,
        format_id=req.format_id,
        quality_preset=req.quality_preset,
        audio_only=req.audio_only,
        subtitles=req.subtitles,
        embed_thumbnail=req.embed_thumbnail,
        sponsorblock=req.sponsorblock,
        output_template=req.output_template or settings.default_output_template,
        options=req.options.model_dump(exclude_none=True) if req.options else {},
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

    if not is_scheduled:
        await manager.enqueue(job.id)
    return CreatedJob(id=job.id)


@router.post("/batch", response_model=CreatedBatch, status_code=201)
async def create_batch(req: BatchRequest, session: Session = Depends(get_session)) -> CreatedBatch:
    """Queue many URLs at once (shared options). Metadata is filled on completion."""
    settings = get_settings(session)
    options = req.options.model_dump(exclude_none=True) if req.options else {}
    audio_only = bool(req.options and req.options.audio_only)

    seen: set[str] = set()
    jobs: list[Job] = []
    for raw in req.urls:
        url = raw.strip()
        if not url or url.startswith("#") or url in seen:
            continue  # skip blanks, comments, and dupes within the batch
        seen.add(url)
        jobs.append(
            Job(
                url=url,
                status=JobStatus.queued,
                audio_only=audio_only,
                output_template=settings.default_output_template,
                options=options,
            )
        )
    if not jobs:
        raise HTTPException(status_code=422, detail="No valid URLs in the batch.")

    session.add_all(jobs)
    session.commit()
    ids = []
    for job in jobs:
        session.refresh(job)
        ids.append(job.id)
    for jid in ids:
        await manager.enqueue(jid)
    return CreatedBatch(ids=ids, count=len(ids))


@router.post("/reorder", response_model=JobList)
def reorder_downloads(req: ReorderRequest, session: Session = Depends(get_session)) -> JobList:
    """Rewrite queue_position over the currently-queued jobs in the given order.

    Ids that are unknown or no longer queued are skipped. Queued jobs omitted
    from the payload keep their relative order and sort after the listed ones.
    """
    queued = session.exec(
        select(Job)
        .where(Job.status == JobStatus.queued)
        .order_by(Job.queue_position, Job.created_at)
    ).all()
    by_id = {j.id: j for j in queued}

    seen: set[int] = set()
    listed = []
    for i in req.ordered_ids:
        if i in by_id and i not in seen:
            seen.add(i)
            listed.append(by_id[i])
    listed_ids = {j.id for j in listed}
    ordered = listed + [j for j in queued if j.id not in listed_ids]

    for pos, job in enumerate(ordered, start=1):
        job.queue_position = pos
        job.updated_at = utcnow()
    session.commit()

    items = [_job_read(j) for j in ordered]
    return JobList(items=items, total=len(items), page=1, page_size=max(1, len(items)))


@router.post("/cancel", response_model=BulkCancelResult)
def cancel_downloads(req: BulkCancelRequest, session: Session = Depends(get_session)) -> BulkCancelResult:
    """Cancel many jobs at once. Unknown or already-terminal ids are skipped."""
    cancelled = 0
    for jid in req.ids:
        job = session.get(Job, jid)
        if job is None or job.status in TERMINAL_STATES:
            continue
        manager.cancel(jid)
        cancelled += 1
    return BulkCancelResult(cancelled=cancelled)


@router.get("/active", response_model=JobList)
def list_active_downloads(session: Session = Depends(get_session)) -> JobList:
    """All non-terminal jobs (scheduled/queued/downloading/post-processing), in
    queue order. Uncapped: the Queue page must show every pending job, which a
    paginated created_at-ordered list cannot guarantee (queued jobs run oldest-first)."""
    items = session.exec(
        select(Job)
        .where(Job.status.in_(_ACTIVE_STATES))
        .order_by(Job.queue_position, Job.created_at)
    ).all()
    return JobList(
        items=[_job_read(j) for j in items],
        total=len(items),
        page=1,
        page_size=max(1, len(items)),
    )


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

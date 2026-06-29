"""GET /api/files/{id} — serve the finished file for download."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session

from ..db import get_session
from ..models import Job, JobStatus

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/{job_id}")
def get_file(job_id: int, session: Session = Depends(get_session)) -> FileResponse:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != JobStatus.completed or not job.filepath:
        raise HTTPException(status_code=409, detail="File is not ready.")
    if not os.path.exists(job.filepath):
        raise HTTPException(status_code=404, detail="File no longer exists on disk.")
    return FileResponse(
        job.filepath,
        filename=os.path.basename(job.filepath),
        media_type="application/octet-stream",
    )

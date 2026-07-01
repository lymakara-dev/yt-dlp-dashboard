"""POST /api/probe — extract metadata + formats without downloading."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from ..downloader import ProbeError, probe, probe_raw
from ..schemas import ProbeRequest, ProbeResponse

router = APIRouter(prefix="/api", tags=["probe"])


@router.post("/probe", response_model=ProbeResponse)
async def probe_url(req: ProbeRequest) -> ProbeResponse:
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=422, detail="URL is required.")
    try:
        # Run blocking extraction off the event loop.
        return await asyncio.to_thread(probe, url)
    except ProbeError as exc:
        # Surface a readable message, not a 500.
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/probe/raw")
async def probe_url_raw(req: ProbeRequest) -> dict:
    """Return the full sanitized yt-dlp info JSON (developer / raw extraction)."""
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=422, detail="URL is required.")
    try:
        return await asyncio.to_thread(probe_raw, url)
    except ProbeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

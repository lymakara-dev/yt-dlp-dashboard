"""POST /api/probe — extract metadata + formats without downloading."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from ..downloader import ProbeError, probe
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

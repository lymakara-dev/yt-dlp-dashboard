"""POST /api/artist/expand — flatten a channel/playlist URL into individual videos."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from ..downloader import ProbeError, expand_entries
from ..schemas import ArtistExpandRequest, ArtistExpandResponse, SearchResultItem

router = APIRouter(prefix="/api/artist", tags=["artist"])


@router.post("/expand", response_model=ArtistExpandResponse)
async def expand_artist(req: ArtistExpandRequest) -> ArtistExpandResponse:
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=422, detail="URL is required.")
    try:
        result = await asyncio.to_thread(expand_entries, url, limit=req.limit)
    except ProbeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ArtistExpandResponse(
        title=result["title"],
        uploader=result["uploader"],
        entries=[SearchResultItem(**e) for e in result["entries"]],
    )

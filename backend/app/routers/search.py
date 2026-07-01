"""POST /api/search — search a provider (ytsearch/ytsearchdate/scsearch)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from ..downloader import ProbeError, search
from ..schemas import SearchRequest, SearchResponse, SearchResultItem

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search_videos(req: SearchRequest) -> SearchResponse:
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Search query is required.")
    try:
        results = await asyncio.to_thread(
            search, query, limit=req.limit, provider=req.provider
        )
    except ProbeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SearchResponse(results=[SearchResultItem(**r) for r in results])

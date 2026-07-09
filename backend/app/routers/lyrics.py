"""POST /api/lyrics/search — fetch lyrics (LRCLIB) + audio candidates (yt-dlp)."""
from __future__ import annotations

import asyncio
from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from ..downloader import ProbeError, search
from ..lyrics import LyricsError, search_lyrics
from ..schemas import (
    LyricsCandidateOut,
    LyricsSearchRequest,
    LyricsSearchResponse,
    SearchResultItem,
)

router = APIRouter(prefix="/api", tags=["lyrics"])


@router.post("/lyrics/search", response_model=LyricsSearchResponse)
async def lyrics_search(req: LyricsSearchRequest) -> LyricsSearchResponse:
    track = req.track.strip()
    artist = req.artist.strip()
    if not track or not artist:
        raise HTTPException(status_code=422, detail="Track and artist are required.")

    async def _lyrics() -> tuple[list, bool]:
        try:
            result = await asyncio.to_thread(search_lyrics, track, artist, limit=req.limit)
            return result, True
        except LyricsError:
            return [], False

    async def _audio() -> list[dict]:
        try:
            return await asyncio.to_thread(
                search, f"{artist} {track}", limit=req.limit, provider="ytsearch"
            )
        except ProbeError:
            return []

    (lyrics, available), audio = await asyncio.gather(_lyrics(), _audio())

    best_duration = lyrics[0].duration if lyrics else None
    if best_duration:
        audio.sort(key=lambda a: abs((a.get("duration") or 0.0) - best_duration))

    return LyricsSearchResponse(
        lyrics=[LyricsCandidateOut(**asdict(c)) for c in lyrics],
        audio=[SearchResultItem(**a) for a in audio],
        lyrics_available=available,
    )

"""LRCLIB lyrics client — fetch synced/plain lyrics by track + artist.

LRCLIB (https://lrclib.net) is a public, key-free lyrics database. We use its
search endpoint and return candidates; the caller (and ultimately the user)
picks which one to attach to a download.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

LRCLIB_SEARCH_URL = "https://lrclib.net/api/search"
USER_AGENT = "yt-dlp-dashboard (https://github.com/yt-dlp-dashboard)"
_TIMEOUT = 15.0  # LRCLIB search can legitimately take 6-7s; leave headroom


class LyricsError(Exception):
    """Raised when LRCLIB is unreachable or returns an error status."""


@dataclass
class LyricsCandidate:
    track: str | None
    artist: str | None
    album: str | None
    duration: float | None
    synced_lyrics: str | None
    plain_lyrics: str | None


def _to_candidate(item: dict) -> LyricsCandidate:
    return LyricsCandidate(
        track=item.get("trackName"),
        artist=item.get("artistName"),
        album=item.get("albumName"),
        duration=item.get("duration"),
        synced_lyrics=item.get("syncedLyrics"),
        plain_lyrics=item.get("plainLyrics"),
    )


def search_lyrics(
    track: str,
    artist: str,
    duration: float | None = None,
    *,
    limit: int = 5,
) -> list[LyricsCandidate]:
    """Search LRCLIB. Returns up to `limit` candidates (may be empty).

    Raises LyricsError on network / non-2xx failures.
    """
    params = {"track_name": track, "artist_name": artist}
    try:
        resp = httpx.get(
            LRCLIB_SEARCH_URL,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        raise LyricsError(f"Lyrics lookup failed: {exc}") from exc

    items = data if isinstance(data, list) else []
    candidates = [_to_candidate(it) for it in items[:limit]]
    if duration is not None:
        candidates.sort(key=lambda c: abs((c.duration or 0.0) - duration))
    return candidates

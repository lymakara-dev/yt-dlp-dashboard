# Lyrics + Audio Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user search a song by title + artist, fetch synced lyrics and audio candidates, confirm a track, download it as mp3 through the existing queue, and attach the lyrics as both an embedded ID3 tag and a `.lrc` sidecar.

**Architecture:** Two new isolated backend units — an LRCLIB lyrics client (`app/lyrics.py`) and a tag/sidecar writer (`app/tagging.py`) — plus a combined search endpoint (`routers/lyrics.py`) that runs the lyrics lookup and the existing yt-dlp `search()` concurrently. The download itself reuses the existing job queue unchanged; lyrics text rides in the existing `Job.options` JSON blob and is attached inside `run_download` after the file lands. The frontend gets a new "Lyrics" tab that mirrors the existing `SearchPage`.

**Tech Stack:** Python 3.11, FastAPI, SQLModel, yt-dlp (library mode), httpx (LRCLIB HTTP), mutagen (ID3 tagging); React 19 + TypeScript, TanStack Query, Tailwind, shadcn/ui.

## Global Constraints

- Backend Python `>=3.11`; run tests with `backend/.venv/bin/python -m pytest` from the `backend/` directory.
- New runtime dependencies go in `backend/pyproject.toml` under `[project].dependencies`: promote `httpx` from the dev group to runtime, add `mutagen>=1.47`.
- Lyrics source is **LRCLIB only** (`https://lrclib.net/api`), no API key. Always send a `User-Agent` header identifying the app.
- No database migration: new per-download knobs live in `DownloadOptions` (`app/options.py`) and persist inside the existing `Job.options` JSON.
- No Smule, no scraping of any ToS-restricted site — audio comes from the existing yt-dlp `search()` and the user picks the track.
- Ruff line-length 100. Follow existing file patterns (see `routers/search.py`, `components/SearchPage.tsx`).
- All tests run offline — mock `httpx` and use temp files; never hit the network.
- Frontend API field names must match backend Pydantic field names exactly (`schemas.py` is the contract, per its module docstring).

---

### Task 1: LRCLIB lyrics client (`app/lyrics.py`)

**Files:**
- Create: `backend/app/lyrics.py`
- Create: `backend/tests/test_lyrics.py`
- Modify: `backend/pyproject.toml` (promote `httpx` to runtime deps)

**Interfaces:**
- Consumes: nothing (leaf module).
- Produces:
  - `@dataclass LyricsCandidate` with fields `track: str | None`, `artist: str | None`, `album: str | None`, `duration: float | None`, `synced_lyrics: str | None`, `plain_lyrics: str | None`.
  - `class LyricsError(Exception)`.
  - `def search_lyrics(track: str, artist: str, duration: float | None = None, *, limit: int = 5) -> list[LyricsCandidate]` — calls `httpx.get`, returns up to `limit` candidates; sorts by closeness to `duration` when given; returns `[]` on empty results; raises `LyricsError` on any `httpx.HTTPError` / non-2xx.

- [ ] **Step 1: Promote httpx to a runtime dependency**

Edit `backend/pyproject.toml`. In `[project].dependencies` add the line `"httpx>=0.27",` and remove `"httpx>=0.27",` from the `[dependency-groups].dev` list (leave `pytest` there). httpx is already installed in `.venv`, so no install is needed.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_lyrics.py`:

```python
from types import SimpleNamespace

import httpx
import pytest

from app import lyrics


def _fake_response(payload, status=200):
    def _get(url, params=None, headers=None, timeout=None):
        req = httpx.Request("GET", url)
        return httpx.Response(status, json=payload, request=req)
    return _get


def test_search_lyrics_parses_candidates(monkeypatch):
    payload = [
        {
            "trackName": "Yesterday",
            "artistName": "The Beatles",
            "albumName": "Help!",
            "duration": 125.0,
            "plainLyrics": "Yesterday...",
            "syncedLyrics": "[00:00.00] Yesterday...",
        }
    ]
    monkeypatch.setattr(lyrics.httpx, "get", _fake_response(payload))
    out = lyrics.search_lyrics("Yesterday", "The Beatles")
    assert len(out) == 1
    assert out[0].track == "Yesterday"
    assert out[0].artist == "The Beatles"
    assert out[0].synced_lyrics == "[00:00.00] Yesterday..."
    assert out[0].plain_lyrics == "Yesterday..."


def test_search_lyrics_sorts_by_duration(monkeypatch):
    payload = [
        {"trackName": "A", "artistName": "X", "duration": 300.0,
         "plainLyrics": "a", "syncedLyrics": None},
        {"trackName": "B", "artistName": "X", "duration": 200.0,
         "plainLyrics": "b", "syncedLyrics": None},
    ]
    monkeypatch.setattr(lyrics.httpx, "get", _fake_response(payload))
    out = lyrics.search_lyrics("A", "X", duration=205.0)
    assert out[0].track == "B"  # 200 is closest to 205


def test_search_lyrics_empty_is_not_error(monkeypatch):
    monkeypatch.setattr(lyrics.httpx, "get", _fake_response([]))
    assert lyrics.search_lyrics("Nothing", "Nobody") == []


def test_search_lyrics_raises_on_http_error(monkeypatch):
    def _boom(url, params=None, headers=None, timeout=None):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(lyrics.httpx, "get", _boom)
    with pytest.raises(lyrics.LyricsError):
        lyrics.search_lyrics("A", "B")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_lyrics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.lyrics'`.

- [ ] **Step 4: Write minimal implementation**

Create `backend/app/lyrics.py`:

```python
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
_TIMEOUT = 10.0


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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_lyrics.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/lyrics.py backend/tests/test_lyrics.py backend/pyproject.toml
git commit -m "feat(lyrics): LRCLIB client for synced/plain lyrics search"
```

---

### Task 2: Tag + sidecar writer (`app/tagging.py`)

**Files:**
- Create: `backend/app/tagging.py`
- Create: `backend/tests/test_tagging.py`
- Modify: `backend/pyproject.toml` (add `mutagen`)

**Interfaces:**
- Consumes: nothing (leaf module).
- Produces:
  - `def parse_lrc(lrc: str) -> list[tuple[int, str]]` — parse `[mm:ss.xx] text` lines into `(offset_ms, text)` pairs, sorted by time; ignores non-timestamped lines.
  - `def attach_lyrics(filepath: str, synced_lrc: str | None, plain_text: str | None) -> None` — writes `<basename>.lrc` sidecar (synced preferred, else plain) and, for `.mp3` files, embeds ID3 `USLT` (plain) + `SYLT` (synced, when parseable). Idempotent. Never raises on tag-write issues for non-mp3 files (sidecar still written).

- [ ] **Step 1: Add mutagen dependency and install it**

Edit `backend/pyproject.toml`: add `"mutagen>=1.47",` to `[project].dependencies`.
Run: `cd backend && .venv/bin/python -m pip install "mutagen>=1.47"`
Expected: `Successfully installed mutagen-...`.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_tagging.py`:

```python
import wave

from mutagen.id3 import ID3
from mutagen.mp3 import MP3

from app import tagging

# A tiny valid MP3 (silent frame) encoded so mutagen can add ID3 to it.
# We synthesize one via lameless approach: write a minimal MP3 frame header
# repeated; mutagen only needs a parseable stream to attach ID3 tags.
_MP3_SILENCE = (
    b"\xff\xfb\x90\x00" + b"\x00" * 417
) * 10


def _make_mp3(path):
    path.write_bytes(_MP3_SILENCE)
    return str(path)


def test_parse_lrc_extracts_timed_lines():
    lrc = "[00:01.00] hello\n[00:03.50] world\nno timestamp here\n"
    out = tagging.parse_lrc(lrc)
    assert out == [(1000, "hello"), (3500, "world")]


def test_attach_lyrics_writes_sidecar(tmp_path):
    mp3 = _make_mp3(tmp_path / "song.mp3")
    tagging.attach_lyrics(mp3, "[00:00.00] hi", "hi")
    sidecar = tmp_path / "song.lrc"
    assert sidecar.exists()
    assert sidecar.read_text() == "[00:00.00] hi"


def test_attach_lyrics_embeds_uslt_and_sylt(tmp_path):
    mp3 = _make_mp3(tmp_path / "song.mp3")
    tagging.attach_lyrics(mp3, "[00:00.50] la la", "la la")
    tags = ID3(mp3)
    uslt = tags.getall("USLT")
    sylt = tags.getall("SYLT")
    assert uslt and uslt[0].text == "la la"
    assert sylt and sylt[0].text == [("la la", 500)]


def test_attach_lyrics_plain_only_no_sylt(tmp_path):
    mp3 = _make_mp3(tmp_path / "song.mp3")
    tagging.attach_lyrics(mp3, None, "just plain")
    tags = ID3(mp3)
    assert tags.getall("USLT")[0].text == "just plain"
    assert tags.getall("SYLT") == []
    # sidecar falls back to plain text
    assert (tmp_path / "song.lrc").read_text() == "just plain"


def test_attach_lyrics_idempotent(tmp_path):
    mp3 = _make_mp3(tmp_path / "song.mp3")
    tagging.attach_lyrics(mp3, "[00:00.00] x", "x")
    tagging.attach_lyrics(mp3, "[00:00.00] x", "x")
    tags = ID3(mp3)
    assert len(tags.getall("USLT")) == 1
    assert len(tags.getall("SYLT")) == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_tagging.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.tagging'`.

- [ ] **Step 4: Write minimal implementation**

Create `backend/app/tagging.py`:

```python
"""Attach lyrics to a downloaded audio file: .lrc sidecar + embedded ID3 tags.

Sidecar is written for any audio file. ID3 embedding (USLT + SYLT) applies to
.mp3 files via mutagen. Tag-write failures are non-fatal to the caller.
"""
from __future__ import annotations

import logging
import os
import re

from mutagen.id3 import ID3, SYLT, USLT
from mutagen.id3._util import ID3NoHeaderError

log = logging.getLogger(__name__)

_LRC_LINE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")


def parse_lrc(lrc: str) -> list[tuple[int, str]]:
    """Parse `[mm:ss.xx] text` lines into (offset_ms, text), sorted by time."""
    out: list[tuple[int, str]] = []
    for line in lrc.splitlines():
        m = _LRC_LINE.match(line.strip())
        if not m:
            continue
        minutes, seconds, text = m.group(1), m.group(2), m.group(3)
        offset_ms = int((int(minutes) * 60 + float(seconds)) * 1000)
        out.append((offset_ms, text.strip()))
    out.sort(key=lambda p: p[0])
    return out


def _write_sidecar(filepath: str, synced_lrc: str | None, plain_text: str | None) -> None:
    content = synced_lrc if synced_lrc else plain_text
    if not content:
        return
    base = os.path.splitext(filepath)[0]
    with open(f"{base}.lrc", "w", encoding="utf-8") as fh:
        fh.write(content)


def _embed_id3(filepath: str, synced_lrc: str | None, plain_text: str | None) -> None:
    try:
        tags = ID3(filepath)
    except ID3NoHeaderError:
        tags = ID3()
    tags.delall("USLT")
    tags.delall("SYLT")
    if plain_text:
        tags.add(USLT(encoding=3, lang="eng", desc="", text=plain_text))
    if synced_lrc:
        timed = parse_lrc(synced_lrc)
        if timed:
            # SYLT.text is [(text, ms), ...]; format=2 => absolute ms, type=1 => lyrics.
            tags.add(
                SYLT(
                    encoding=3,
                    lang="eng",
                    format=2,
                    type=1,
                    desc="",
                    text=[(text, ms) for ms, text in timed],
                )
            )
    tags.save(filepath)


def attach_lyrics(filepath: str, synced_lrc: str | None, plain_text: str | None) -> None:
    """Write a .lrc sidecar and (for .mp3) embed USLT/SYLT tags."""
    if not synced_lrc and not plain_text:
        return
    _write_sidecar(filepath, synced_lrc, plain_text)
    if filepath.lower().endswith(".mp3"):
        try:
            _embed_id3(filepath, synced_lrc, plain_text)
        except Exception as exc:  # tag-write must never break the download
            log.warning("Could not embed lyrics into %s: %s", filepath, exc)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_tagging.py -v`
Expected: PASS (5 passed). If the synthetic MP3 fails to parse in `MP3(...)`, note the tests use `ID3(...)` directly which only needs a file to attach to — this is intentional.

- [ ] **Step 6: Commit**

```bash
git add backend/app/tagging.py backend/tests/test_tagging.py backend/pyproject.toml
git commit -m "feat(lyrics): .lrc sidecar + ID3 USLT/SYLT tag writer"
```

---

### Task 3: Lyrics options fields (`app/options.py`)

**Files:**
- Modify: `backend/app/options.py` (add two fields to `DownloadOptions`)
- Modify: `backend/tests/test_options.py` (add a field round-trip test)

**Interfaces:**
- Consumes: nothing new.
- Produces: `DownloadOptions.lyrics_synced: str | None` and `DownloadOptions.lyrics_plain: str | None`, defaulting to `None`, carried through `model_dump(exclude_none=True)` and `merge_legacy`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_options.py`:

```python
def test_download_options_carry_lyrics():
    from app.options import DownloadOptions, merge_legacy

    o = DownloadOptions(lyrics_synced="[00:00.00] hi", lyrics_plain="hi")
    dumped = o.model_dump(exclude_none=True)
    assert dumped["lyrics_synced"] == "[00:00.00] hi"
    assert dumped["lyrics_plain"] == "hi"

    merged = merge_legacy(
        format_id=None, quality_preset=None, audio_only=True,
        subtitles=False, embed_thumbnail=False, sponsorblock=False,
        options={"lyrics_synced": "[00:00.00] hi", "lyrics_plain": "hi"},
    )
    assert merged.lyrics_synced == "[00:00.00] hi"
    assert merged.lyrics_plain == "hi"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_options.py::test_download_options_carry_lyrics -v`
Expected: FAIL with `KeyError: 'lyrics_synced'` (field not yet present).

- [ ] **Step 3: Add the fields**

In `backend/app/options.py`, inside `class DownloadOptions`, immediately after the `# ---- audio extraction ----` block (after the `ffmpeg_args` field), add:

```python
    # ---- lyrics (title+artist lyrics feature) ----
    lyrics_synced: str | None = None  # LRC-format synced lyrics to attach
    lyrics_plain: str | None = None  # plain lyrics fallback to attach
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_options.py -v`
Expected: PASS (all option tests, including the new one).

- [ ] **Step 5: Commit**

```bash
git add backend/app/options.py backend/tests/test_options.py
git commit -m "feat(lyrics): add lyrics_synced/lyrics_plain download options"
```

---

### Task 4: Attach lyrics after download (`app/downloader.py`)

**Files:**
- Modify: `backend/app/downloader.py` (`run_download` + new helper + logging import)
- Create: `backend/tests/test_lyrics_attach.py`

**Interfaces:**
- Consumes: `DownloadOptions.lyrics_synced` / `lyrics_plain` (Task 3); `tagging.attach_lyrics` (Task 2).
- Produces: `run_download` calls `attach_lyrics(result["filepath"], options.lyrics_synced, options.lyrics_plain)` when a filepath exists and either lyrics field is set. Failure is logged, never raised.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_lyrics_attach.py`:

```python
from app import downloader
from app.options import DownloadOptions


def test_maybe_attach_lyrics_calls_tagging(monkeypatch, tmp_path):
    called = {}

    def fake_attach(path, synced, plain):
        called["args"] = (path, synced, plain)

    monkeypatch.setattr("app.tagging.attach_lyrics", fake_attach)
    f = tmp_path / "song.mp3"
    f.write_bytes(b"x")
    opts = DownloadOptions(lyrics_synced="[00:00.00] hi", lyrics_plain="hi")
    downloader._maybe_attach_lyrics(opts, str(f))
    assert called["args"] == (str(f), "[00:00.00] hi", "hi")


def test_maybe_attach_lyrics_noop_without_lyrics(monkeypatch, tmp_path):
    called = {"n": 0}
    monkeypatch.setattr(
        "app.tagging.attach_lyrics", lambda *a: called.__setitem__("n", called["n"] + 1)
    )
    downloader._maybe_attach_lyrics(DownloadOptions(), str(tmp_path / "s.mp3"))
    assert called["n"] == 0


def test_maybe_attach_lyrics_swallows_errors(monkeypatch, tmp_path):
    def boom(*a):
        raise RuntimeError("nope")

    monkeypatch.setattr("app.tagging.attach_lyrics", boom)
    opts = DownloadOptions(lyrics_plain="hi")
    # Must not raise.
    downloader._maybe_attach_lyrics(opts, str(tmp_path / "s.mp3"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_lyrics_attach.py -v`
Expected: FAIL with `AttributeError: module 'app.downloader' has no attribute '_maybe_attach_lyrics'`.

- [ ] **Step 3: Add logging import and the helper**

In `backend/app/downloader.py`, add near the top imports (after `import shutil`):

```python
import logging
```

And after the existing `import` block, add a module logger (place it just below the imports, before `class ProbeError`):

```python
log = logging.getLogger(__name__)
```

Add this helper immediately above `def run_download(`:

```python
def _maybe_attach_lyrics(options: DownloadOptions, filepath: str | None) -> None:
    """Attach lyrics to a finished file when the job carries lyrics text.

    Imported lazily so mutagen stays an optional import path. Never raises.
    """
    if not filepath:
        return
    synced = options.lyrics_synced
    plain = options.lyrics_plain
    if not synced and not plain:
        return
    try:
        from .tagging import attach_lyrics

        attach_lyrics(filepath, synced, plain)
    except Exception as exc:
        log.warning("Attaching lyrics failed for %s: %s", filepath, exc)
```

- [ ] **Step 4: Call it in `run_download`**

In `backend/app/downloader.py`, change the tail of `run_download` from:

```python
    return _extract_result(info)
```

to:

```python
    result = _extract_result(info)
    _maybe_attach_lyrics(options, result.get("filepath"))
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_lyrics_attach.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/downloader.py backend/tests/test_lyrics_attach.py
git commit -m "feat(lyrics): attach lyrics to finished download in run_download"
```

---

### Task 5: Combined lyrics search endpoint (`routers/lyrics.py`)

**Files:**
- Create: `backend/app/routers/lyrics.py`
- Modify: `backend/app/schemas.py` (request/response models)
- Modify: `backend/app/main.py` (register the router)
- Create: `backend/tests/test_lyrics_router.py`

**Interfaces:**
- Consumes: `lyrics.search_lyrics` (Task 1); `downloader.search` + `downloader.ProbeError` (existing).
- Produces: `POST /api/lyrics/search` accepting `{track, artist, limit?}` and returning `{lyrics: LyricsCandidateOut[], audio: SearchResultItem[], lyrics_available: bool}`. Audio is sorted by closeness to the best lyric candidate's duration. LRCLIB failure degrades to `lyrics=[]`, `lyrics_available=false` without failing the request.

- [ ] **Step 1: Add schemas**

In `backend/app/schemas.py`, after the `# ---------- Search ----------` block (after `SearchResponse`), add:

```python
# ---------- Lyrics ----------
class LyricsSearchRequest(BaseModel):
    track: str
    artist: str
    limit: int = 5


class LyricsCandidateOut(BaseModel):
    track: str | None = None
    artist: str | None = None
    album: str | None = None
    duration: float | None = None
    synced_lyrics: str | None = None
    plain_lyrics: str | None = None


class LyricsSearchResponse(BaseModel):
    lyrics: list[LyricsCandidateOut] = []
    audio: list[SearchResultItem] = []
    lyrics_available: bool = True  # False when LRCLIB was unreachable
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_lyrics_router.py`:

```python
from fastapi.testclient import TestClient

from app.lyrics import LyricsCandidate, LyricsError
from app.main import app

client = TestClient(app)


def _cand(track, dur):
    return LyricsCandidate(
        track=track, artist="X", album=None, duration=dur,
        synced_lyrics=f"[00:00.00] {track}", plain_lyrics=track,
    )


def test_lyrics_search_combines_results(monkeypatch):
    monkeypatch.setattr(
        "app.routers.lyrics.search_lyrics", lambda *a, **k: [_cand("Song", 200.0)]
    )
    audio = [
        {"url": "u1", "title": "far", "uploader": "c", "duration": 400.0,
         "thumbnail": None, "view_count": None},
        {"url": "u2", "title": "near", "uploader": "c", "duration": 205.0,
         "thumbnail": None, "view_count": None},
    ]
    monkeypatch.setattr("app.routers.lyrics.search", lambda *a, **k: audio)

    resp = client.post("/api/lyrics/search", json={"track": "Song", "artist": "X"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["lyrics_available"] is True
    assert body["lyrics"][0]["synced_lyrics"] == "[00:00.00] Song"
    # audio sorted by closeness to lyric duration (200): "near" (205) first
    assert body["audio"][0]["url"] == "u2"


def test_lyrics_search_degrades_when_lrclib_down(monkeypatch):
    def boom(*a, **k):
        raise LyricsError("down")

    monkeypatch.setattr("app.routers.lyrics.search_lyrics", boom)
    monkeypatch.setattr("app.routers.lyrics.search", lambda *a, **k: [])
    resp = client.post("/api/lyrics/search", json={"track": "S", "artist": "X"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["lyrics_available"] is False
    assert body["lyrics"] == []


def test_lyrics_search_requires_track_and_artist():
    resp = client.post("/api/lyrics/search", json={"track": "  ", "artist": "X"})
    assert resp.status_code == 422
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_lyrics_router.py -v`
Expected: FAIL — 404 on the endpoint (router not registered) / import error.

- [ ] **Step 4: Create the router**

Create `backend/app/routers/lyrics.py`:

```python
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
```

- [ ] **Step 5: Register the router**

In `backend/app/main.py`:
- Change the import line `from .routers import downloads, files, probe, search, settings, ws` to include `lyrics`: `from .routers import downloads, files, lyrics, probe, search, settings, ws`.
- After `app.include_router(search.router)` add: `app.include_router(lyrics.router)`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_lyrics_router.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/lyrics.py backend/app/schemas.py backend/app/main.py backend/tests/test_lyrics_router.py
git commit -m "feat(lyrics): POST /api/lyrics/search combining LRCLIB + yt-dlp search"
```

---

### Task 6: Frontend types + API client

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`

**Interfaces:**
- Consumes: backend `POST /api/lyrics/search` (Task 5) and its response shape.
- Produces: TS types `LyricsCandidate`, `LyricsSearchResponse`; `DownloadOptions` gains `lyrics_synced?` / `lyrics_plain?`; `api.lyricsSearch(track, artist, limit)` returning `Promise<LyricsSearchResponse>`.

- [ ] **Step 1: Add types**

In `frontend/src/lib/types.ts`, inside `interface DownloadOptions` add (near the audio fields):

```typescript
  lyrics_synced?: string | null;
  lyrics_plain?: string | null;
```

And after `SearchResponse` add:

```typescript
export interface LyricsCandidate {
  track: string | null;
  artist: string | null;
  album: string | null;
  duration: number | null;
  synced_lyrics: string | null;
  plain_lyrics: string | null;
}

export interface LyricsSearchResponse {
  lyrics: LyricsCandidate[];
  audio: SearchResultItem[];
  lyrics_available: boolean;
}
```

- [ ] **Step 2: Add the API method**

In `frontend/src/lib/api.ts`:
- Add `LyricsSearchResponse` to the type import block from `./types`.
- Inside the `api` object, after the `search:` method, add:

```typescript
  lyricsSearch: (track: string, artist: string, limit = 5) =>
    request<LyricsSearchResponse>("/api/lyrics/search", {
      method: "POST",
      body: JSON.stringify({ track, artist, limit }),
    }),
```

- [ ] **Step 3: Verify the frontend still type-checks**

Run: `cd frontend && npm run build`
Expected: build succeeds (no TS errors). If the project exposes `npm run typecheck`, run that instead.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "feat(lyrics): frontend types + lyricsSearch API client"
```

---

### Task 7: Frontend Lyrics page + navigation

**Files:**
- Create: `frontend/src/components/LyricsPage.tsx`
- Modify: `frontend/src/components/Header.tsx` (add `lyrics` to `View` + nav)
- Modify: `frontend/src/App.tsx` (render the page)

**Interfaces:**
- Consumes: `api.lyricsSearch` + `api.createDownload` (Task 6); `LyricsCandidate`, `SearchResultItem`, `LyricsSearchResponse` types.
- Produces: a `LyricsPage` component; `View` union includes `"lyrics"`.

- [ ] **Step 1: Add the nav entry**

In `frontend/src/components/Header.tsx`:
- Change `export type View = "home" | "queue" | "search" | "history" | "settings";` to `export type View = "home" | "queue" | "search" | "lyrics" | "history" | "settings";`.
- Add `Music` to the `lucide-react` import.
- Add to the `NAV` array after the search entry: `{ key: "lyrics", label: "Lyrics", icon: Music },`.

- [ ] **Step 2: Create the page component**

Create `frontend/src/components/LyricsPage.tsx`:

```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, Loader2, Music } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import type { LyricsCandidate, SearchResultItem } from "@/lib/types";

export function LyricsPage() {
  const qc = useQueryClient();
  const [track, setTrack] = useState("");
  const [artist, setArtist] = useState("");
  const [selected, setSelected] = useState(0); // index into lyrics candidates

  const search = useMutation({
    mutationFn: () => api.lyricsSearch(track.trim(), artist.trim()),
    onSuccess: () => setSelected(0),
    onError: (e: ApiError) => toast.error("Search failed", { description: e.message }),
  });

  const create = useMutation({
    mutationFn: (url: string) => {
      const lyric = search.data?.lyrics[selected];
      return api.createDownload({
        url,
        options: {
          audio_only: true,
          audio_format: "mp3",
          lyrics_synced: lyric?.synced_lyrics ?? null,
          lyrics_plain: lyric?.plain_lyrics ?? null,
        },
      });
    },
    onSuccess: () => {
      toast.success("Download queued with lyrics");
      qc.invalidateQueries({ queryKey: ["downloads"] });
    },
    onError: (e: ApiError) =>
      toast.error("Could not start download", { description: e.message }),
  });

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (track.trim() && artist.trim()) search.mutate();
  };

  const data = search.data;
  const lyrics = data?.lyrics ?? [];
  const audio = data?.audio ?? [];
  const current = lyrics[selected];

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-3 p-5 sm:p-6">
          <form onSubmit={onSearch} className="flex flex-col gap-2 sm:flex-row">
            <Input
              value={track}
              onChange={(e) => setTrack(e.target.value)}
              placeholder="Song title…"
              autoFocus
              className="h-11 text-base"
            />
            <Input
              value={artist}
              onChange={(e) => setArtist(e.target.value)}
              placeholder="Artist…"
              className="h-11 text-base"
            />
            <Button
              type="submit"
              size="lg"
              disabled={search.isPending || !track.trim() || !artist.trim()}
            >
              {search.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Music className="h-4 w-4" />
              )}
              Find
            </Button>
          </form>
        </CardContent>
      </Card>

      {data && !data.lyrics_available && (
        <p className="text-sm text-amber-600">
          Lyrics service was unreachable — you can still download audio without lyrics.
        </p>
      )}

      {lyrics.length > 0 && (
        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex flex-wrap gap-2">
              {lyrics.map((l, i) => (
                <button
                  key={`${l.track}-${i}`}
                  type="button"
                  onClick={() => setSelected(i)}
                  className={
                    "rounded-md border px-2.5 py-1 text-xs " +
                    (i === selected
                      ? "border-primary bg-secondary"
                      : "text-muted-foreground")
                  }
                >
                  {l.track ?? "?"} — {l.artist ?? "?"}
                  {l.duration ? ` · ${formatDuration(l.duration)}` : ""}
                </button>
              ))}
            </div>
            <LyricsPreview candidate={current} />
          </CardContent>
        </Card>
      )}

      {data && lyrics.length === 0 && data.lyrics_available && (
        <p className="text-sm text-muted-foreground">
          No lyrics found. Pick an audio track to download without lyrics.
        </p>
      )}

      {audio.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium">Pick the matching track:</p>
          {audio.map((r) => (
            <AudioRow
              key={r.url ?? r.title}
              result={r}
              onDownload={() => r.url && create.mutate(r.url)}
              downloading={create.isPending}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function LyricsPreview({ candidate }: { candidate: LyricsCandidate | undefined }) {
  if (!candidate) return null;
  const text = candidate.synced_lyrics ?? candidate.plain_lyrics ?? "";
  return (
    <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-muted p-3 text-xs">
      {text || "No preview available."}
    </pre>
  );
}

function AudioRow({
  result,
  onDownload,
  downloading,
}: {
  result: SearchResultItem;
  onDownload: () => void;
  downloading: boolean;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-3">
        {result.thumbnail ? (
          <img
            src={result.thumbnail}
            alt=""
            className="h-14 w-24 shrink-0 rounded object-cover"
            loading="lazy"
          />
        ) : (
          <div className="h-14 w-24 shrink-0 rounded bg-muted" />
        )}
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{result.title ?? "Untitled"}</div>
          <div className="truncate text-xs text-muted-foreground">
            {[result.uploader, result.duration ? formatDuration(result.duration) : null]
              .filter(Boolean)
              .join(" · ")}
          </div>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={onDownload}
          disabled={downloading || !result.url}
        >
          <Download className="h-4 w-4" />
          Queue mp3 + lyrics
        </Button>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 3: Wire it into App**

In `frontend/src/App.tsx`:
- Add `import { LyricsPage } from "@/components/LyricsPage";` with the other component imports.
- After the `search` view block, add:

```tsx
        {view === "lyrics" && (
          <div className="space-y-4">
            <h1 className="text-xl font-semibold">Lyrics + Audio</h1>
            <LyricsPage />
          </div>
        )}
```

- [ ] **Step 4: Verify the frontend builds**

Run: `cd frontend && npm run build`
Expected: build succeeds, no TS errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/LyricsPage.tsx frontend/src/components/Header.tsx frontend/src/App.tsx
git commit -m "feat(lyrics): Lyrics page with candidate preview + confirm-to-download"
```

---

### Task 8: Full test run + documentation

**Files:**
- Modify: `README.md` (document the feature + endpoint)

- [ ] **Step 1: Run the entire backend test suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all tests pass (existing + new `test_lyrics.py`, `test_tagging.py`, `test_lyrics_attach.py`, `test_lyrics_router.py`, and the added `test_options.py` case).

- [ ] **Step 2: Document the feature**

In `README.md`, under the **Features** section, add a bullet group:

```markdown
**Lyrics + Audio**
- Search a song by **title + artist**; the dashboard fetches synced lyrics from
  [LRCLIB](https://lrclib.net) and audio candidates via yt-dlp search side by side.
- You confirm which track to download; it grabs the mp3 through the normal queue
  and attaches the lyrics as an embedded ID3 tag (`USLT`/`SYLT`) **and** a `.lrc`
  sidecar file next to the audio.
```

And in the **API Reference** section, add a row/entry:

```markdown
- `POST /api/lyrics/search` — body `{ track, artist, limit? }`; returns
  `{ lyrics[], audio[], lyrics_available }`. Combines an LRCLIB lyrics lookup with
  a yt-dlp audio search; audio is sorted by closeness to the best lyric duration.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document lyrics + audio download feature and endpoint"
```

---

## Self-Review Notes

- **Spec coverage:** search-by-title+artist (Tasks 5–7), LRCLIB synced+plain (Task 1), concurrent lyrics+audio lookup (Task 5), user-confirms-track (Task 7), reuse existing download pipeline (Task 4), embed ID3 + `.lrc` sidecar (Task 2), no-lyrics/degraded handling (Tasks 5 & 7), no-DB-migration via `Job.options` (Task 3), offline tests (all tasks), no Smule/scraping (audio via existing `search()`). All spec sections map to a task.
- **Out-of-scope items** (batch, translation, editor, auto-pick) are intentionally absent.
- **Type consistency:** `LyricsCandidate` fields (`track/artist/album/duration/synced_lyrics/plain_lyrics`) are identical across `lyrics.py`, `schemas.py` (`LyricsCandidateOut`), and `types.ts`. `attach_lyrics(filepath, synced_lrc, plain_text)` signature is consistent between Task 2 (definition), Task 4 (call), and their tests. Options field names `lyrics_synced`/`lyrics_plain` match across backend options, downloader, schemas usage, and frontend.

# Lyrics + Audio Download — Design

**Date:** 2026-07-09
**Status:** Approved (design), pending implementation plan

## Summary

Add a "Lyrics" mode to the yt-dlp Dashboard: the user searches for a song by
**title + artist**, the app fetches **synced lyrics** from a lyrics database and
**audio candidates** via the existing yt-dlp search, the user **confirms** which
audio track to download, and the finished mp3 gets its lyrics attached both as an
embedded ID3 tag and as a `.lrc` sidecar file.

This is the legitimate framing of the original request. It does **not** scrape
Smule or any site that prohibits it; lyrics come from a public lyrics API and
audio comes from the same source the dashboard already downloads from, with the
user choosing the track.

## Scope

### In scope
- Search by title + artist.
- Fetch synced (`.lrc`) + plain lyrics candidates from LRCLIB (free, no API key).
- Fetch audio candidates via the existing `downloader.search()` (yt-dlp `ytsearch`).
- User confirms which audio track to download (no silent auto-download).
- Download audio as mp3 through the **existing** download queue/pipeline.
- Attach lyrics to the finished file: embed ID3 `USLT` (always) + `SYLT` (if
  synced lyrics exist) **and** write a `<basename>.lrc` sidecar.
- Graceful handling when no lyrics or no audio match is found.
- Unit tests for the lyrics client, the tag writer, and the router (all offline).

### Explicitly out of scope (YAGNI)
- Scraping Smule or any ToS-restricted site.
- Playlist / batch lyrics fetching.
- Lyrics translation.
- An in-app lyrics editor.
- Auto-pick without confirmation.

## Architecture & Flow

```
User enters: track title + artist
        │
        ▼
POST /api/lyrics/search
   ├─ ① LRCLIB      → synced (.lrc) + plain lyrics candidates
   └─ ② yt-dlp      → audio candidates (title, channel, duration, id, thumbnail)
        │  (① and ② run concurrently)
        ▼
Frontend: lyrics preview + audio candidate list  →  USER confirms one track
        │
        ▼
POST /api/downloads   (EXISTING endpoint)
   audio_only = mp3
   options.lyrics_synced / options.lyrics_plain = chosen lyrics text
        │
        ▼
Existing download queue downloads the mp3
        │
        ▼
NEW post-process step: attach_lyrics()
   ├─ write <basename>.lrc sidecar
   └─ embed ID3 USLT (plain) + SYLT (synced, if available)
        │
        ▼
Completed job in History, flagged as having lyrics
```

The only new runtime surface is the **search-and-confirm** step and the
**tag/sidecar writer**. The download itself reuses the existing async job queue
unchanged.

## Components

Each unit has one clear purpose, a well-defined interface, and is independently
testable.

### 1. `app/lyrics.py` — LRCLIB client
- **Interface:** `async def search_lyrics(track: str, artist: str, duration: float | None = None) -> list[LyricsCandidate]`
- `LyricsCandidate`: `{ track, artist, album, duration, synced_lyrics, plain_lyrics }`.
- Calls LRCLIB (`GET https://lrclib.net/api/search?track_name=&artist_name=`);
  optionally refines with `/api/get` when duration is known for an exact match.
- Pure HTTP + parse. No side effects. Depends on `httpx`.
- **Errors:** network / non-200 → raise a typed `LyricsError`; empty results →
  return `[]` (not an error).

### 2. `app/tagging.py` — tag + sidecar writer
- **Interface:** `def attach_lyrics(filepath: str, synced_lrc: str | None, plain_text: str | None) -> None`
- Writes `<basename>.lrc` next to the audio file when `synced_lrc` (or plain, as
  fallback) is present.
- Embeds ID3 frames via `mutagen`: `USLT` (unsynchronised, plain text) always
  when text exists; `SYLT` (synchronised) when `synced_lrc` is present and
  parseable into timestamped lines.
- Idempotent: re-running replaces existing lyric frames rather than duplicating.
- Depends on `mutagen`. No network.

### 3. `app/routers/lyrics.py` — search endpoint
- **Interface:** `POST /api/lyrics/search` with `{ track, artist, limit? }`.
- Runs `search_lyrics(...)` and the existing `downloader.search(...)`
  **concurrently** (`asyncio.gather`).
- Returns `{ lyrics: LyricsCandidate[], audio: SearchResultItem[] }`.
- Sorts/annotates audio candidates by closeness to the best lyric candidate's
  duration to surface a "best guess," but does not auto-select.

### 4. `downloader.py` — post-process hook (extend)
- After a successful **mp3** download, if the job's `options` carry
  `lyrics_synced` / `lyrics_plain`, call `attach_lyrics(final_path, ...)`.
- Failure to attach lyrics logs a warning and marks the job completed with a
  non-fatal note; it does **not** fail the download.

### 5. `options.py` / `schemas.py` — options fields (extend)
- Add `lyrics_synced: str | None` and `lyrics_plain: str | None` to the download
  options model.
- Stored inside the existing `Job.options` JSON blob — **no DB migration**
  (per the model's documented design intent).

### 6. Frontend — Lyrics page
- New tab/mode: title + artist form.
- On search: show lyrics preview (with candidate switcher if multiple) and the
  audio candidate list (title, channel, duration, thumbnail; best guess marked).
- User picks an audio candidate → POST to the existing downloads endpoint with
  the chosen lyrics text in options.
- History surfaces a small "lyrics attached" indicator (reuses existing history
  view; minimal addition).

## Dependencies
- **`httpx`** — promote from dev-only to a runtime dependency (LRCLIB calls).
- **`mutagen`** — new runtime dependency (ID3 `USLT`/`SYLT` writing).

Both are small, widely used, and pure-Python.

## Error Handling
- **No lyrics found:** UI states it; user may pick a different lyric candidate or
  download audio-only anyway. Lyrics are never silently guessed/attached wrong.
- **No audio match / download failure:** existing queue error handling applies;
  nothing lyric-specific destabilizes the queue.
- **LRCLIB unreachable:** search endpoint still returns audio candidates with an
  empty lyrics list and a flag so the UI can explain the degraded result.
- **Tag write failure:** non-fatal; job completes, warning logged, `.lrc` sidecar
  still attempted independently of tag embedding.

## Testing (TDD, matches existing `tests/` layout)
- `test_lyrics.py`: `search_lyrics` against mocked httpx responses — happy path,
  empty results, network error, duration-refined match.
- `test_tagging.py`: `attach_lyrics` writes a `.lrc` sidecar and embeds
  `USLT`/`SYLT` into a temp mp3; read frames back to assert; idempotency check.
- `test_lyrics_router.py` (or extend `test_api.py`): `POST /api/lyrics/search`
  with both LRCLIB and yt-dlp search mocked — combined response shape, degraded
  (no-lyrics) path.
- All tests run offline; no real network calls.

## Legitimacy note
LRCLIB is a community lyrics database intended for programmatic access. Audio is
fetched from the same source the dashboard already supports, and the user selects
the specific track. The feature deliberately avoids Smule and any scraping of
sites whose terms forbid it, consistent with the project's existing "Responsible
Use" section.

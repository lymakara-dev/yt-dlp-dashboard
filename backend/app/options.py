"""The canonical, extensible set of per-download options.

`DownloadOptions` is the single source of truth for every yt-dlp knob the
dashboard exposes. It is:

* accepted on the API (nested under `DownloadRequest.options`),
* persisted verbatim as JSON on `Job.options` (so a job is reproducible and
  survives restarts without a schema migration per new option), and
* translated into a `YoutubeDL` options dict by `downloader.build_ydl_opts`.

Adding a new feature is usually: add a field here, translate it in the
downloader, mirror it in the frontend `DownloadOptions` type, and surface it in
the Options UI. Everything is optional with a safe default so old persisted
jobs and old clients keep working.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class DownloadOptions(BaseModel):
    """Every configurable download knob. All fields optional / defaulted."""

    # ---- format selection ----
    # A raw yt-dlp format selector (advanced mode). When set it wins over
    # format_id / quality_preset.
    format_selector: str | None = None
    format_id: str | None = None
    quality_preset: str | None = None  # best | 1080p | 720p | audio
    audio_only: bool = False

    # ---- subtitles / thumbnails / metadata (legacy simple toggles) ----
    subtitles: bool = False
    embed_thumbnail: bool = False
    sponsorblock: bool = False

    model_config = {"extra": "ignore"}


def merge_legacy(
    *,
    format_id: str | None,
    quality_preset: str | None,
    audio_only: bool,
    subtitles: bool,
    embed_thumbnail: bool,
    sponsorblock: bool,
    options: dict | None,
) -> DownloadOptions:
    """Build a `DownloadOptions` from a job's persisted state.

    The seven legacy top-level columns are the historical contract; the
    `options` JSON blob carries everything newer. Legacy columns win only when
    the blob does not already specify the same knob, so re-submitting an old job
    behaves identically.
    """
    data: dict = dict(options or {})
    data.setdefault("format_id", format_id)
    data.setdefault("quality_preset", quality_preset)
    data.setdefault("audio_only", audio_only)
    data.setdefault("subtitles", subtitles)
    data.setdefault("embed_thumbnail", embed_thumbnail)
    data.setdefault("sponsorblock", sponsorblock)
    return DownloadOptions.model_validate(data)

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

    # ---- subtitles (granular) ----
    write_subs: bool = False  # download real (uploaded) subtitles
    write_auto_subs: bool = False  # download auto-generated subtitles
    sub_langs: list[str] = Field(default_factory=list)  # e.g. ["en", "es", "en.*"]
    embed_subs: bool = False  # mux subtitles into the video container
    convert_subs: str | None = None  # convert to srt | ass | vtt | lrc

    # ---- thumbnails (granular) ----
    write_thumbnail: bool = False  # save the thumbnail as a separate file
    write_all_thumbnails: bool = False  # save every available thumbnail
    convert_thumbnail: str | None = None  # convert to jpg | png | webp

    # ---- audio extraction ----
    audio_format: str | None = None  # mp3|aac|opus|flac|wav|vorbis|m4a (with audio_only)
    audio_quality: str | None = None  # 0 (best) .. 10, or a kbps value like "192"
    keep_audio_codec: bool = False  # copy the source codec instead of converting
    normalize_audio: bool = False  # apply ffmpeg loudnorm during extraction
    ffmpeg_args: str | None = None  # raw args appended to ffmpeg postprocessors

    # ---- metadata ----
    write_info_json: bool = False  # write the full .info.json sidecar
    embed_metadata: bool = False  # embed title/uploader/date/description in-container
    embed_chapters: bool = False  # embed chapter markers
    write_comments: bool = False  # fetch comments (stored in .info.json)
    preserve_mtime: bool = True  # set file mtime to the upload date

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

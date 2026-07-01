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

    # ---- file organization ----
    output_template: str | None = None  # per-download output/folder template override
    use_archive: bool = False  # record downloads in an archive to prevent duplicates

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

    # ---- download control ----
    rate_limit: str | None = None  # max speed, e.g. "2M", "500K" (bytes/s)
    retries: int | None = None  # retries per download
    fragment_retries: int | None = None  # retries per fragment
    retry_delay: int | None = None  # seconds to sleep between retries
    concurrent_fragments: int | None = None  # parallel fragment downloads (N)
    resume: bool = True  # resume partial downloads (continuedl)
    download_sections: str | None = None  # e.g. "*10:00-15:00" or a chapter regex
    max_filesize: str | None = None  # skip files larger than this, e.g. "500M"
    min_filesize: str | None = None  # skip files smaller than this, e.g. "1M"

    # ---- cookies ----
    cookies_from_browser: str | None = None  # chrome|chromium|edge|firefox|brave|opera|vivaldi|safari
    cookies_file: str | None = None  # path to a Netscape cookies.txt

    # ---- authentication ----
    username: str | None = None  # login (use "oauth2" for extractors that support it)
    password: str | None = None
    video_password: str | None = None  # password for a specific protected video
    twofactor: str | None = None  # 2FA / OTP code
    netrc: bool = False  # read credentials from ~/.netrc

    # ---- network ----
    proxy: str | None = None  # http://host:port or socks5://host:port
    source_address: str | None = None  # bind to a local interface/IP
    force_ip: str | None = None  # "ipv4" | "ipv6" (overridden by source_address)
    user_agent: str | None = None
    referer: str | None = None
    http_headers: str | None = None  # newline-separated "Key: Value" pairs
    geo_bypass: bool = True  # fake X-Forwarded-For to bypass geo restrictions
    geo_bypass_country: str | None = None  # ISO 3166-2 code, e.g. "US"

    # ---- playlist ----
    playlist: bool = False  # download the whole playlist (not just one video)
    playlist_items: str | None = None  # range/selection, e.g. "1-10,15,20:30"
    playlist_reverse: bool = False
    playlist_random: bool = False
    skip_unavailable: bool = False  # continue past unavailable/errored entries
    lazy_playlist: bool = False  # stream entries as they are parsed
    ignore_duplicates: bool = False  # download archive to skip already-downloaded videos

    model_config = {"extra": "ignore"}


# Keys whose values must never be echoed back to the client (history/detail).
SENSITIVE_KEYS = frozenset({"password", "video_password", "twofactor"})


def redact(options: dict | None) -> dict:
    """Return a copy of an options dict with secret values masked."""
    result = dict(options or {})
    for key in SENSITIVE_KEYS:
        if result.get(key):
            result[key] = "********"
    return result


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

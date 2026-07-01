"""Thin wrappers around yt-dlp's YoutubeDL used as a library (no shelling out)."""
from __future__ import annotations

import shutil
from typing import Any, Callable

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from .options import DownloadOptions
from .schemas import FormatInfo, ProbeResponse


class ProbeError(Exception):
    """Raised when extraction fails; carries a human-readable message."""


def ffmpeg_info() -> tuple[bool, str | None]:
    """Return (available, version_string)."""
    path = shutil.which("ffmpeg")
    if not path:
        return False, None
    import subprocess

    try:
        out = subprocess.run(
            [path, "-version"], capture_output=True, text=True, timeout=5
        )
        first = out.stdout.splitlines()[0] if out.stdout else None
        return True, first
    except Exception:
        return True, None


def _resolution(fmt: dict[str, Any]) -> str | None:
    if fmt.get("resolution"):
        return fmt["resolution"]
    w, h = fmt.get("width"), fmt.get("height")
    if w and h:
        return f"{w}x{h}"
    if h:
        return f"{h}p"
    return None


def _parse_formats(info: dict[str, Any]) -> list[FormatInfo]:
    formats: list[FormatInfo] = []
    for fmt in info.get("formats", []) or []:
        fid = fmt.get("format_id")
        if not fid:
            continue
        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")
        audio_only = (vcodec in (None, "none")) and acodec not in (None, "none")
        video_only = (acodec in (None, "none")) and vcodec not in (None, "none")
        formats.append(
            FormatInfo(
                format_id=str(fid),
                ext=fmt.get("ext"),
                resolution=_resolution(fmt),
                fps=fmt.get("fps"),
                vcodec=None if vcodec == "none" else vcodec,
                acodec=None if acodec == "none" else acodec,
                filesize=fmt.get("filesize") or fmt.get("filesize_approx"),
                format_note=fmt.get("format_note"),
                audio_only=audio_only,
                video_only=video_only,
            )
        )
    return formats


def probe(url: str) -> ProbeResponse:
    """Extract metadata + available formats WITHOUT downloading.

    Raises ProbeError with a readable message on failure.
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": False,
        # Only flatten the playlist listing; we still want full formats for a
        # single video. extract_flat in_playlist keeps single-video extraction full.
        "extract_flat": "in_playlist",
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except (DownloadError, ExtractorError) as exc:
        raise ProbeError(_clean_message(str(exc))) from exc
    except Exception as exc:  # network / unexpected
        raise ProbeError(f"Could not read this URL: {exc}") from exc

    if info is None:
        raise ProbeError("No information could be extracted from this URL.")

    is_playlist = info.get("_type") == "playlist" or "entries" in info
    if is_playlist:
        entries = [e for e in (info.get("entries") or []) if e]
        first = entries[0] if entries else {}
        return ProbeResponse(
            url=url,
            title=info.get("title") or first.get("title"),
            uploader=info.get("uploader") or first.get("uploader"),
            duration=None,
            thumbnail=info.get("thumbnail") or first.get("thumbnail"),
            is_playlist=True,
            playlist_count=info.get("playlist_count") or len(entries),
            formats=[],  # formats are per-entry for playlists
        )

    return ProbeResponse(
        url=url,
        title=info.get("title"),
        uploader=info.get("uploader"),
        duration=info.get("duration"),
        thumbnail=info.get("thumbnail"),
        is_playlist=False,
        playlist_count=None,
        formats=_parse_formats(info),
    )


def _clean_message(msg: str) -> str:
    """Strip yt-dlp's ANSI / ERROR: prefixes for a friendlier UI message."""
    msg = msg.replace("\x1b[0;31m", "").replace("\x1b[0m", "")
    for prefix in ("ERROR: ", "\033[0;31mERROR:\033[0m "):
        if msg.startswith(prefix):
            msg = msg[len(prefix):]
    return msg.strip()


# ---------------------------------------------------------------------------
# Download (phase 2)
# ---------------------------------------------------------------------------
ProgressHook = Callable[[dict[str, Any]], None]

QUALITY_PRESETS: dict[str, str] = {
    "best": "bv*+ba/b",
    "1080p": "bv*[height<=1080]+ba/b[height<=1080]/b",
    "720p": "bv*[height<=720]+ba/b[height<=720]/b",
    "audio": "bestaudio/best",
}


class DownloadCancelled(Exception):
    """Raised from inside a progress hook to abort an in-flight download."""


class DownloadFailed(Exception):
    """Wraps a yt-dlp DownloadError with a readable message."""


def _select_format(o: DownloadOptions) -> str:
    """Resolve the yt-dlp format selector string from the options."""
    if o.format_selector:
        return o.format_selector
    if o.audio_only:
        return o.format_id or "bestaudio/best"
    if o.format_id:
        # Advanced pick: try the exact format, fall back to merging audio, then best.
        return f"{o.format_id}+ba/{o.format_id}/b"
    return QUALITY_PRESETS.get(o.quality_preset or "best", QUALITY_PRESETS["best"])


def build_ydl_opts(
    o: DownloadOptions,
    *,
    download_dir: str,
    output_template: str,
    progress_hooks: list[ProgressHook],
    postprocessor_hooks: list[ProgressHook],
) -> dict[str, Any]:
    """Translate dashboard options into a YoutubeDL options dict."""
    postprocessors: list[dict[str, Any]] = []

    # ---- format selection ----
    fmt = _select_format(o)
    if o.audio_only:
        postprocessors.append(
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        )

    opts: dict[str, Any] = {
        "format": fmt,
        "paths": {"home": download_dir},
        "outtmpl": {"default": output_template},
        "progress_hooks": progress_hooks,
        "postprocessor_hooks": postprocessor_hooks,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "noprogress": True,
        "ignoreerrors": False,
        "merge_output_format": "mp4",
        "windowsfilenames": False,
        "restrictfilenames": False,
    }

    # ---- subtitles ----
    # Legacy `subtitles` toggle == download uploaded+auto English subs and embed.
    write_subs = o.write_subs or o.subtitles
    write_auto = o.write_auto_subs or o.subtitles
    embed_subs = o.embed_subs or o.subtitles
    if write_subs or write_auto:
        if write_subs:
            opts["writesubtitles"] = True
        if write_auto:
            opts["writeautomaticsub"] = True
        opts["subtitleslangs"] = o.sub_langs or ["en.*"]
        if embed_subs and not o.audio_only:
            postprocessors.append({"key": "FFmpegEmbedSubtitle"})
        if o.convert_subs:
            postprocessors.append(
                {"key": "FFmpegSubtitlesConvertor", "format": o.convert_subs}
            )

    # ---- thumbnails ----
    if o.write_thumbnail or o.embed_thumbnail or o.convert_thumbnail:
        opts["writethumbnail"] = True
    if o.write_all_thumbnails:
        opts["writethumbnail"] = True
        opts["write_all_thumbnails"] = True
    if o.convert_thumbnail:
        # Runs before EmbedThumbnail so the embedded art is the converted one.
        postprocessors.append(
            {"key": "FFmpegThumbnailsConvertor", "format": o.convert_thumbnail}
        )
    if o.embed_thumbnail:
        postprocessors.append({"key": "EmbedThumbnail"})

    if o.sponsorblock:
        postprocessors.append({"key": "SponsorBlock", "categories": ["sponsor"]})
        postprocessors.append(
            {"key": "ModifyChapters", "remove_sponsor_segments": ["sponsor"]}
        )

    if postprocessors:
        opts["postprocessors"] = postprocessors

    return opts


def run_download(
    *,
    url: str,
    download_dir: str,
    output_template: str,
    options: DownloadOptions,
    on_event: ProgressHook,
    is_cancelled: Callable[[], bool],
) -> dict[str, Any]:
    """Run a blocking download. Intended to be called inside a thread executor.

    `on_event` receives normalized payload dicts (see _normalize). `is_cancelled`
    is polled from the progress hook so cancellation can interrupt the download.
    Returns a result dict with filepath/filesize/metadata on success.
    """

    def _progress_hook(d: dict[str, Any]) -> None:
        if is_cancelled():
            raise DownloadCancelled()
        on_event(_normalize_progress(d))

    def _pp_hook(d: dict[str, Any]) -> None:
        if is_cancelled():
            raise DownloadCancelled()
        on_event(_normalize_pp(d))

    opts = build_ydl_opts(
        options,
        download_dir=download_dir,
        output_template=output_template,
        progress_hooks=[_progress_hook],
        postprocessor_hooks=[_pp_hook],
    )

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            info = ydl.sanitize_info(info)
    except DownloadCancelled:
        raise
    except (DownloadError, ExtractorError) as exc:
        raise DownloadFailed(_clean_message(str(exc))) from exc
    except Exception as exc:
        raise DownloadFailed(f"Download failed: {exc}") from exc

    return _extract_result(info)


def _extract_result(info: dict[str, Any]) -> dict[str, Any]:
    filepath: str | None = None
    filesize: int | None = None
    requested = info.get("requested_downloads") or []
    if requested:
        rd = requested[0]
        filepath = rd.get("filepath") or rd.get("_filename")
        filesize = rd.get("filesize") or rd.get("filesize_approx")
    if filepath is None:
        filepath = info.get("filepath") or info.get("_filename")

    import os

    if filepath and filesize is None and os.path.exists(filepath):
        filesize = os.path.getsize(filepath)

    ext = None
    if filepath:
        ext = os.path.splitext(filepath)[1].lstrip(".") or None

    return {
        "filepath": filepath,
        "filesize": filesize,
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "ext": ext or info.get("ext"),
    }


def _normalize_progress(d: dict[str, Any]) -> dict[str, Any]:
    status = d.get("status")  # downloading | finished | error
    total = d.get("total_bytes") or d.get("total_bytes_estimate")
    downloaded = d.get("downloaded_bytes")
    progress = None
    if total and downloaded is not None:
        progress = max(0.0, min(100.0, downloaded / total * 100.0))
    elif status == "finished":
        progress = 100.0
    return {
        "kind": "progress",
        "status": status,
        "progress": progress,
        "downloaded_bytes": downloaded,
        "total_bytes": total,
        "speed": d.get("speed"),
        "eta": d.get("eta"),
        "filename": d.get("filename"),
        "fragment_index": d.get("fragment_index"),
        "fragment_count": d.get("fragment_count"),
    }


def _normalize_pp(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "postprocess",
        "status": d.get("status"),  # started | processing | finished
        "postprocessor": d.get("postprocessor"),
    }

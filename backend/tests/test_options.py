"""Translation of DownloadOptions into YoutubeDL option dicts."""
from __future__ import annotations

import pytest

from app.downloader import build_ydl_opts, parse_bytes, parse_download_sections
from app.options import DownloadOptions, merge_legacy


def _build(o: DownloadOptions) -> dict:
    return build_ydl_opts(
        o,
        download_dir="/tmp/dl",
        output_template="%(title)s.%(ext)s",
        progress_hooks=[],
        postprocessor_hooks=[],
    )


def _pp_keys(opts: dict) -> list[str]:
    return [p["key"] for p in opts.get("postprocessors", [])]


def test_default_preset_best():
    opts = _build(DownloadOptions())
    assert opts["format"] == "bv*+ba/b"
    assert opts["paths"] == {"home": "/tmp/dl"}
    assert "postprocessors" not in opts


def test_quality_presets():
    assert _build(DownloadOptions(quality_preset="1080p"))["format"].startswith("bv*[height<=1080]")
    assert _build(DownloadOptions(quality_preset="720p"))["format"].startswith("bv*[height<=720]")


def test_audio_only_extracts_mp3():
    opts = _build(DownloadOptions(audio_only=True))
    assert opts["format"] == "bestaudio/best"
    assert "FFmpegExtractAudio" in _pp_keys(opts)


def test_format_id_merges_audio():
    opts = _build(DownloadOptions(format_id="137"))
    assert opts["format"] == "137+ba/137/b"


def test_raw_format_selector_wins():
    opts = _build(DownloadOptions(format_selector="bestvideo[height<=720]+bestaudio"))
    assert opts["format"] == "bestvideo[height<=720]+bestaudio"


@pytest.mark.parametrize(
    "selector",
    [
        "best",
        "worst",
        "bv*+ba/b",
        "bv*[fps>=60]+ba/b",
        "bv*[vcodec^=av01]+ba/b",
        "bv*[dynamic_range*=HDR]+ba/b",
        "bv*[tbr<=2000]+ba/b",
        "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
    ],
)
def test_arbitrary_selectors_pass_through(selector):
    # Even when a format_id/preset is also set, the raw selector wins verbatim.
    opts = _build(DownloadOptions(format_selector=selector, format_id="137", quality_preset="720p"))
    assert opts["format"] == selector


def test_subtitles_and_thumbnail_and_sponsorblock():
    opts = _build(
        DownloadOptions(subtitles=True, embed_thumbnail=True, sponsorblock=True)
    )
    assert opts["writesubtitles"] is True
    assert opts["writeautomaticsub"] is True
    keys = _pp_keys(opts)
    assert "FFmpegEmbedSubtitle" in keys
    assert "EmbedThumbnail" in keys
    assert "SponsorBlock" in keys
    assert "ModifyChapters" in keys


def test_granular_subtitles_langs_and_convert():
    opts = _build(
        DownloadOptions(
            write_subs=True,
            write_auto_subs=True,
            sub_langs=["en", "es"],
            embed_subs=True,
            convert_subs="srt",
        )
    )
    assert opts["writesubtitles"] is True
    assert opts["writeautomaticsub"] is True
    assert opts["subtitleslangs"] == ["en", "es"]
    keys = _pp_keys(opts)
    assert "FFmpegEmbedSubtitle" in keys
    assert "FFmpegSubtitlesConvertor" in keys


def test_write_subs_without_embed_saves_separately():
    opts = _build(DownloadOptions(write_subs=True, sub_langs=["fr"]))
    assert opts["writesubtitles"] is True
    assert "writeautomaticsub" not in opts
    assert "FFmpegEmbedSubtitle" not in _pp_keys(opts)


def test_audio_only_never_embeds_subs():
    opts = _build(DownloadOptions(audio_only=True, subtitles=True))
    assert "FFmpegEmbedSubtitle" not in _pp_keys(opts)


def test_thumbnail_write_all_and_convert_and_embed():
    opts = _build(
        DownloadOptions(
            write_all_thumbnails=True, convert_thumbnail="png", embed_thumbnail=True
        )
    )
    assert opts["writethumbnail"] is True
    assert opts["write_all_thumbnails"] is True
    keys = _pp_keys(opts)
    # Convertor must precede EmbedThumbnail so the embedded art is converted.
    assert keys.index("FFmpegThumbnailsConvertor") < keys.index("EmbedThumbnail")


def test_write_thumbnail_only():
    opts = _build(DownloadOptions(write_thumbnail=True))
    assert opts["writethumbnail"] is True
    assert "write_all_thumbnails" not in opts
    assert "EmbedThumbnail" not in _pp_keys(opts)


def test_metadata_info_json_comments_and_embed():
    opts = _build(
        DownloadOptions(
            write_info_json=True,
            write_comments=True,
            embed_metadata=True,
            embed_chapters=True,
        )
    )
    assert opts["writeinfojson"] is True
    assert opts["getcomments"] is True
    meta = [p for p in opts["postprocessors"] if p["key"] == "FFmpegMetadata"]
    assert len(meta) == 1
    assert meta[0]["add_metadata"] is True
    assert meta[0]["add_chapters"] is True


def test_embed_chapters_without_full_metadata():
    opts = _build(DownloadOptions(embed_chapters=True))
    meta = [p for p in opts["postprocessors"] if p["key"] == "FFmpegMetadata"]
    assert meta[0]["add_metadata"] is False
    assert meta[0]["add_chapters"] is True


def test_preserve_mtime_default_and_off():
    assert _build(DownloadOptions())["updatetime"] is True
    assert _build(DownloadOptions(preserve_mtime=False))["updatetime"] is False


def test_audio_format_and_quality():
    opts = _build(DownloadOptions(audio_only=True, audio_format="flac", audio_quality="0"))
    pp = [p for p in opts["postprocessors"] if p["key"] == "FFmpegExtractAudio"][0]
    assert pp["preferredcodec"] == "flac"
    assert pp["preferredquality"] == "0"


def test_keep_audio_codec_uses_best():
    opts = _build(DownloadOptions(audio_only=True, audio_format="mp3", keep_audio_codec=True))
    pp = [p for p in opts["postprocessors"] if p["key"] == "FFmpegExtractAudio"][0]
    assert pp["preferredcodec"] == "best"


def test_normalize_audio_only_on_extraction():
    on = _build(DownloadOptions(audio_only=True, normalize_audio=True))
    assert on["postprocessor_args"]["extractaudio"] == ["-af", "loudnorm"]
    off = _build(DownloadOptions(normalize_audio=True))  # no audio_only -> no-op
    assert "postprocessor_args" not in off


def test_custom_ffmpeg_args_parsed():
    opts = _build(DownloadOptions(ffmpeg_args="-threads 4 -movflags +faststart"))
    assert opts["postprocessor_args"]["default"] == [
        "-threads", "4", "-movflags", "+faststart",
    ]


def test_single_video_stays_noplaylist():
    assert _build(DownloadOptions())["noplaylist"] is True


def test_playlist_options():
    opts = _build(
        DownloadOptions(
            playlist=True,
            playlist_items="1-5,8",
            playlist_reverse=True,
            playlist_random=True,
            lazy_playlist=True,
            skip_unavailable=True,
            ignore_duplicates=True,
        )
    )
    assert opts["noplaylist"] is False
    assert opts["playlist_items"] == "1-5,8"
    assert opts["playlistreverse"] is True
    assert opts["playlistrandom"] is True
    assert opts["lazy_playlist"] is True
    assert opts["ignoreerrors"] is True
    assert opts["download_archive"].endswith("archive.txt")


def test_playlist_items_alone_enables_playlist():
    assert _build(DownloadOptions(playlist_items="1-3"))["noplaylist"] is False


def test_parse_bytes():
    assert parse_bytes("500K") == 512000
    assert parse_bytes("2.5M") == int(2.5 * 1024**2)
    assert parse_bytes("1G") == 1024**3
    assert parse_bytes("1048576") == 1048576
    assert parse_bytes(None) is None
    assert parse_bytes("garbage") is None


def test_download_control_options():
    opts = _build(
        DownloadOptions(
            rate_limit="2M",
            retries=5,
            fragment_retries=10,
            retry_delay=3,
            concurrent_fragments=4,
            resume=False,
            max_filesize="500M",
            min_filesize="1M",
        )
    )
    assert opts["ratelimit"] == 2 * 1024**2
    assert opts["retries"] == 5
    assert opts["fragment_retries"] == 10
    assert opts["retry_sleep_functions"]["http"](0) == 3
    assert opts["concurrent_fragment_downloads"] == 4
    assert opts["continuedl"] is False
    assert opts["max_filesize"] == 500 * 1024**2
    assert opts["min_filesize"] == 1024**2


def test_download_sections_timestamp():
    func = parse_download_sections("*10:00-15:00")
    assert func is not None
    # yt-dlp's range func yields dicts with start/end for a fake info dict.
    ranges = list(func({"duration": 3600}, None))
    assert ranges[0]["start_time"] == 600
    assert ranges[0]["end_time"] == 900


def test_resume_default_leaves_continuedl_unset():
    assert "continuedl" not in _build(DownloadOptions())


def test_merge_legacy_blob_wins_over_columns():
    o = merge_legacy(
        format_id="140",
        quality_preset=None,
        audio_only=True,
        subtitles=False,
        embed_thumbnail=False,
        sponsorblock=False,
        options={"audio_only": False, "format_selector": "worst"},
    )
    # Blob value wins; legacy column fills only what the blob omits.
    assert o.audio_only is False
    assert o.format_selector == "worst"
    assert o.format_id == "140"

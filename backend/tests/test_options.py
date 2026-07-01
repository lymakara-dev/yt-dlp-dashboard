"""Translation of DownloadOptions into YoutubeDL option dicts."""
from __future__ import annotations

from app.downloader import build_ydl_opts
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

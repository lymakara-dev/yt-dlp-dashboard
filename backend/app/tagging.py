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

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

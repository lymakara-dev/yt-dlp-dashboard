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

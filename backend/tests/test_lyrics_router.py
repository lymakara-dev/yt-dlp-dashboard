from fastapi.testclient import TestClient

from app.lyrics import LyricsCandidate, LyricsError
from app.main import app

client = TestClient(app)


def _cand(track, dur):
    return LyricsCandidate(
        track=track, artist="X", album=None, duration=dur,
        synced_lyrics=f"[00:00.00] {track}", plain_lyrics=track,
    )


def test_lyrics_search_combines_results(monkeypatch):
    monkeypatch.setattr(
        "app.routers.lyrics.search_lyrics", lambda *a, **k: [_cand("Song", 200.0)]
    )
    audio = [
        {"url": "u1", "title": "far", "uploader": "c", "duration": 400.0,
         "thumbnail": None, "view_count": None},
        {"url": "u2", "title": "near", "uploader": "c", "duration": 205.0,
         "thumbnail": None, "view_count": None},
    ]
    monkeypatch.setattr("app.routers.lyrics.search", lambda *a, **k: audio)

    resp = client.post("/api/lyrics/search", json={"track": "Song", "artist": "X"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["lyrics_available"] is True
    assert body["lyrics"][0]["synced_lyrics"] == "[00:00.00] Song"
    # audio sorted by closeness to lyric duration (200): "near" (205) first
    assert body["audio"][0]["url"] == "u2"


def test_lyrics_search_degrades_when_lrclib_down(monkeypatch):
    def boom(*a, **k):
        raise LyricsError("down")

    monkeypatch.setattr("app.routers.lyrics.search_lyrics", boom)
    monkeypatch.setattr("app.routers.lyrics.search", lambda *a, **k: [])
    resp = client.post("/api/lyrics/search", json={"track": "S", "artist": "X"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["lyrics_available"] is False
    assert body["lyrics"] == []


def test_lyrics_search_requires_track_and_artist():
    resp = client.post("/api/lyrics/search", json={"track": "  ", "artist": "X"})
    assert resp.status_code == 422

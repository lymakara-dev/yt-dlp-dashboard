from types import SimpleNamespace

import httpx
import pytest

from app import lyrics


def _fake_response(payload, status=200):
    def _get(url, params=None, headers=None, timeout=None):
        req = httpx.Request("GET", url)
        return httpx.Response(status, json=payload, request=req)
    return _get


def test_search_lyrics_parses_candidates(monkeypatch):
    payload = [
        {
            "trackName": "Yesterday",
            "artistName": "The Beatles",
            "albumName": "Help!",
            "duration": 125.0,
            "plainLyrics": "Yesterday...",
            "syncedLyrics": "[00:00.00] Yesterday...",
        }
    ]
    monkeypatch.setattr(lyrics.httpx, "get", _fake_response(payload))
    out = lyrics.search_lyrics("Yesterday", "The Beatles")
    assert len(out) == 1
    assert out[0].track == "Yesterday"
    assert out[0].artist == "The Beatles"
    assert out[0].synced_lyrics == "[00:00.00] Yesterday..."
    assert out[0].plain_lyrics == "Yesterday..."


def test_search_lyrics_sorts_by_duration(monkeypatch):
    payload = [
        {"trackName": "A", "artistName": "X", "duration": 300.0,
         "plainLyrics": "a", "syncedLyrics": None},
        {"trackName": "B", "artistName": "X", "duration": 200.0,
         "plainLyrics": "b", "syncedLyrics": None},
    ]
    monkeypatch.setattr(lyrics.httpx, "get", _fake_response(payload))
    out = lyrics.search_lyrics("A", "X", duration=205.0)
    assert out[0].track == "B"  # 200 is closest to 205


def test_search_lyrics_empty_is_not_error(monkeypatch):
    monkeypatch.setattr(lyrics.httpx, "get", _fake_response([]))
    assert lyrics.search_lyrics("Nothing", "Nobody") == []


def test_search_lyrics_raises_on_http_error(monkeypatch):
    def _boom(url, params=None, headers=None, timeout=None):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(lyrics.httpx, "get", _boom)
    with pytest.raises(lyrics.LyricsError):
        lyrics.search_lyrics("A", "B")

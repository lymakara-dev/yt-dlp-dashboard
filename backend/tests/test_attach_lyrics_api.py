"""POST /api/downloads/{id}/lyrics — attach user-pasted lyrics to a finished file."""
from __future__ import annotations

from app.db import engine
from app.models import Job, JobStatus
from sqlmodel import Session


def _completed_job(tmp_path) -> int:
    mp3 = tmp_path / "song.mp3"
    # Minimal parseable MP3 frame stream so mutagen can attach ID3 tags.
    mp3.write_bytes((b"\xff\xfb\x90\x00" + b"\x00" * 417) * 10)
    with Session(engine) as s:
        job = Job(url="http://x", status=JobStatus.completed, filepath=str(mp3))
        s.add(job)
        s.commit()
        s.refresh(job)
        return job.id


def test_attach_plain_lyrics_writes_sidecar_and_options(client, tmp_path):
    jid = _completed_job(tmp_path)
    r = client.post(f"/api/downloads/{jid}/lyrics", json={"lyrics": "hello\nworld"})
    assert r.status_code == 200
    body = r.json()
    assert body["options"]["lyrics_plain"] == "hello\nworld"
    assert body["options"].get("lyrics_synced") is None
    assert (tmp_path / "song.lrc").read_text() == "hello\nworld"


def test_attach_lrc_lyrics_detected_as_synced(client, tmp_path):
    jid = _completed_job(tmp_path)
    lrc = "[00:01.00] hello\n[00:02.50] world"
    r = client.post(f"/api/downloads/{jid}/lyrics", json={"lyrics": lrc})
    assert r.status_code == 200
    body = r.json()
    assert body["options"]["lyrics_synced"] == lrc
    # plain derived from the timed lines, without timestamps
    assert body["options"]["lyrics_plain"] == "hello\nworld"
    assert (tmp_path / "song.lrc").read_text() == lrc


def test_attach_lyrics_embeds_id3(client, tmp_path):
    from mutagen.id3 import ID3

    jid = _completed_job(tmp_path)
    client.post(f"/api/downloads/{jid}/lyrics", json={"lyrics": "[00:01.00] hi"})
    tags = ID3(str(tmp_path / "song.mp3"))
    assert tags.getall("USLT")[0].text == "hi"
    assert tags.getall("SYLT")[0].text == [("hi", 1000)]


def test_attach_lyrics_rejects_blank(client, tmp_path):
    jid = _completed_job(tmp_path)
    r = client.post(f"/api/downloads/{jid}/lyrics", json={"lyrics": "   "})
    assert r.status_code == 422


def test_attach_lyrics_404_unknown_job(client):
    r = client.post("/api/downloads/99999/lyrics", json={"lyrics": "hi"})
    assert r.status_code == 404


def test_attach_lyrics_409_when_not_completed(client, tmp_path):
    with Session(engine) as s:
        job = Job(url="http://x", status=JobStatus.downloading, filepath=None)
        s.add(job)
        s.commit()
        s.refresh(job)
        jid = job.id
    r = client.post(f"/api/downloads/{jid}/lyrics", json={"lyrics": "hi"})
    assert r.status_code == 409

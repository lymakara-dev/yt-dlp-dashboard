"""GET /api/files/{id}/lyrics — serve the .lrc sidecar for a completed job."""
from __future__ import annotations

from app.db import engine
from app.models import Job, JobStatus
from sqlmodel import Session


def _completed_job(tmp_path, *, with_lrc: bool) -> int:
    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"ID3fake-audio")
    if with_lrc:
        (tmp_path / "song.lrc").write_text("[00:00.00] hi", encoding="utf-8")
    with Session(engine) as s:
        job = Job(url="http://x", status=JobStatus.completed, filepath=str(mp3))
        s.add(job)
        s.commit()
        s.refresh(job)
        return job.id


def test_get_lyrics_file_serves_sidecar(client, tmp_path):
    jid = _completed_job(tmp_path, with_lrc=True)
    r = client.get(f"/api/files/{jid}/lyrics")
    assert r.status_code == 200
    assert r.text == "[00:00.00] hi"
    assert "song.lrc" in r.headers.get("content-disposition", "")


def test_get_lyrics_file_404_when_no_sidecar(client, tmp_path):
    jid = _completed_job(tmp_path, with_lrc=False)
    r = client.get(f"/api/files/{jid}/lyrics")
    assert r.status_code == 404


def test_get_lyrics_file_404_for_unknown_job(client):
    r = client.get("/api/files/99999/lyrics")
    assert r.status_code == 404


def test_get_lyrics_file_409_when_not_completed(client, tmp_path):
    mp3 = tmp_path / "x.mp3"
    mp3.write_bytes(b"x")
    with Session(engine) as s:
        job = Job(url="http://x", status=JobStatus.downloading, filepath=str(mp3))
        s.add(job)
        s.commit()
        s.refresh(job)
        jid = job.id
    r = client.get(f"/api/files/{jid}/lyrics")
    assert r.status_code == 409


def test_delete_with_file_also_removes_lrc_sidecar(client, tmp_path):
    jid = _completed_job(tmp_path, with_lrc=True)
    mp3 = tmp_path / "song.mp3"
    lrc = tmp_path / "song.lrc"
    assert mp3.exists() and lrc.exists()
    r = client.request("DELETE", f"/api/downloads/{jid}", json={"delete_file": True})
    assert r.status_code == 204
    assert not mp3.exists()
    assert not lrc.exists()  # sidecar cleaned up alongside the audio


def test_delete_keeps_files_when_delete_file_false(client, tmp_path):
    jid = _completed_job(tmp_path, with_lrc=True)
    r = client.request("DELETE", f"/api/downloads/{jid}", json={"delete_file": False})
    assert r.status_code == 204
    assert (tmp_path / "song.mp3").exists()
    assert (tmp_path / "song.lrc").exists()  # history-only removal leaves disk untouched

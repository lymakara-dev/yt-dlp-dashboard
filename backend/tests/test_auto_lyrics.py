"""Best-effort auto-lyrics attach after a job completes (queue._maybe_attach_lyrics)."""
from __future__ import annotations

import asyncio

from app.db import engine
from app.lyrics import LyricsCandidate, LyricsError
from app.models import Job, JobStatus
from app.queue import JobManager
from sqlmodel import Session


def _make_completed_job(**overrides) -> int:
    defaults = dict(
        url="https://example.com/watch?v=1",
        status=JobStatus.completed,
        title="Some Song",
        uploader="Some Artist",
        duration=200.0,
        filepath="/tmp/does-not-need-to-exist.mp3",
        options={},
    )
    defaults.update(overrides)
    with Session(engine) as s:
        job = Job(**defaults)
        s.add(job)
        s.commit()
        s.refresh(job)
        return job.id


def test_attaches_lyrics_on_close_duration_match(monkeypatch):
    job_id = _make_completed_job()

    candidate = LyricsCandidate(
        track="Some Song", artist="Some Artist", album=None,
        duration=202.0, synced_lyrics="[00:01.00]la la la", plain_lyrics="la la la",
    )
    monkeypatch.setattr("app.queue.search_lyrics", lambda *a, **k: [candidate])
    attached = []
    monkeypatch.setattr(
        "app.queue.attach_lyrics",
        lambda filepath, synced, plain: attached.append((filepath, synced, plain)),
    )

    mgr = JobManager()
    asyncio.run(mgr._maybe_attach_lyrics(job_id))

    assert attached == [("/tmp/does-not-need-to-exist.mp3", "[00:01.00]la la la", "la la la")]
    with Session(engine) as s:
        job = s.get(Job, job_id)
        assert job.options["lyrics_synced"] == "[00:01.00]la la la"
        assert job.options["lyrics_plain"] == "la la la"


def test_skips_when_no_candidates(monkeypatch):
    job_id = _make_completed_job()
    monkeypatch.setattr("app.queue.search_lyrics", lambda *a, **k: [])
    attached = []
    monkeypatch.setattr("app.queue.attach_lyrics", lambda *a, **k: attached.append(a))

    asyncio.run(JobManager()._maybe_attach_lyrics(job_id))

    assert attached == []
    with Session(engine) as s:
        assert s.get(Job, job_id).options == {}


def test_skips_on_duration_mismatch(monkeypatch):
    job_id = _make_completed_job(duration=200.0)
    candidate = LyricsCandidate(
        track="Some Song", artist="Some Artist", album=None,
        duration=60.0,  # way off from the 200s track
        synced_lyrics="[00:01.00]nope", plain_lyrics="nope",
    )
    monkeypatch.setattr("app.queue.search_lyrics", lambda *a, **k: [candidate])
    attached = []
    monkeypatch.setattr("app.queue.attach_lyrics", lambda *a, **k: attached.append(a))

    asyncio.run(JobManager()._maybe_attach_lyrics(job_id))

    assert attached == []


def test_skips_on_lyrics_error(monkeypatch):
    job_id = _make_completed_job()

    def _boom(*a, **k):
        raise LyricsError("down")

    monkeypatch.setattr("app.queue.search_lyrics", _boom)

    asyncio.run(JobManager()._maybe_attach_lyrics(job_id))  # should not raise

    with Session(engine) as s:
        assert s.get(Job, job_id).options == {}


def test_skips_when_job_not_completed(monkeypatch):
    job_id = _make_completed_job(status=JobStatus.error, filepath=None)
    called = []
    monkeypatch.setattr("app.queue.search_lyrics", lambda *a, **k: called.append(1) or [])

    asyncio.run(JobManager()._maybe_attach_lyrics(job_id))

    assert called == []

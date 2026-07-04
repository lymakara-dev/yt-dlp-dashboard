"""Smoke tests for API wiring (no network / no lifespan)."""
from __future__ import annotations

from app.main import app


def test_expected_routes_registered():
    paths = set(app.openapi()["paths"].keys())
    for path in (
        "/api/probe",
        "/api/probe/raw",
        "/api/search",
        "/api/downloads",
        "/api/downloads/batch",
        "/api/settings",
        "/api/health",
    ):
        assert path in paths, f"missing route {path}"


def test_jobread_exposes_queue_position():
    from app.models import Job, JobStatus
    from app.schemas import JobRead

    job = Job(id=1, url="https://x", status=JobStatus.queued, queue_position=3)
    read = JobRead.model_validate(job)
    assert read.queue_position == 3

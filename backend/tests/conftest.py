"""Test fixtures: isolated temp SQLite DB + FastAPI test client.

The DB env var is set at import time (before any app import) so the engine,
created at module import in app.db, points at a throwaway file.
"""
from __future__ import annotations

import os
import tempfile

_TMPDIR = tempfile.mkdtemp(prefix="ytdlp-test-")
os.environ["YTDLP_DATABASE_URL"] = f"sqlite:///{_TMPDIR}/test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Job  # noqa: E402
from sqlmodel import Session  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    """Fresh schema + empty job table around every test."""
    init_db()
    with Session(engine) as s:
        s.query(Job).delete()
        s.commit()
    yield
    with Session(engine) as s:
        s.query(Job).delete()
        s.commit()


@pytest.fixture
def client():
    # No `with` block: lifespan (worker pool / watcher) is intentionally NOT run.
    return TestClient(app)

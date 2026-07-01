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
        "/api/settings",
        "/api/health",
    ):
        assert path in paths, f"missing route {path}"

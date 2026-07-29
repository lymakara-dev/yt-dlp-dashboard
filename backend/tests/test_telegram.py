"""Telegram bot: allowlist, shared job-creation path, confirm flow, status endpoint."""
from __future__ import annotations

import asyncio

from app.config import config
from app.db import engine, get_settings
from app.jobs import build_job
from app.models import Job
from app.schemas import ProbeResponse
from app.telegram_bot import PendingRequest, TelegramBot, _is_allowed
from sqlmodel import Session, select


def _fake_probe(*, title="Test Song", uploader="Test Artist", duration=180.0):
    def _probe(url: str) -> ProbeResponse:
        return ProbeResponse(
            url=url,
            title=title,
            uploader=uploader,
            duration=duration,
            thumbnail=None,
            is_playlist=False,
        )

    return _probe


# ---------- allowlist ----------
def test_is_allowed_denies_when_empty():
    assert _is_allowed(12345, "") is False


def test_is_allowed_denies_unknown_id():
    assert _is_allowed(12345, "111,222") is False


def test_is_allowed_allows_listed_id():
    assert _is_allowed(222, "111, 222") is True


# ---------- shared job-creation path ----------
def test_build_job_probes_and_persists(monkeypatch):
    monkeypatch.setattr("app.jobs.probe", _fake_probe(title="Some Video"))
    with Session(engine) as session:
        job = asyncio.run(build_job(session, "https://example.com/watch?v=1", audio_only=True))
        assert job.id is not None
        assert job.audio_only is True
        assert job.title == "Some Video"
        assert job.status.value == "queued"


# ---------- confirm flow ----------
def test_handle_url_creates_pending_request(monkeypatch):
    monkeypatch.setattr("app.telegram_bot.probe", _fake_probe())
    bot = TelegramBot()

    sent: list[tuple] = []

    async def fake_send_message(chat_id, text, reply_markup=None):
        sent.append((chat_id, text, reply_markup))
        return {}

    monkeypatch.setattr(bot, "_send_message", fake_send_message)

    asyncio.run(bot._handle_url(555, "https://example.com/watch?v=1"))

    assert len(bot._pending) == 1
    token, pending = next(iter(bot._pending.items()))
    assert pending.url == "https://example.com/watch?v=1"
    assert pending.chat_id == 555
    assert len(sent) == 1
    chat_id, text, reply_markup = sent[0]
    assert chat_id == 555
    assert "Test Song" in text
    buttons = [b["callback_data"] for row in reply_markup["inline_keyboard"] for b in row]
    assert f"dl:{token}:video" in buttons
    assert f"dl:{token}:audio" in buttons


def test_callback_confirm_creates_audio_job(monkeypatch):
    monkeypatch.setattr("app.jobs.probe", _fake_probe(title="Confirmed Song"))
    with Session(engine) as session:
        get_settings(session).telegram_allowed_chat_ids = "999"
        session.commit()

    bot = TelegramBot()
    token = "abc123"
    bot._pending[token] = PendingRequest(
        url="https://example.com/watch?v=2", chat_id=999, created_at=0.0
    )

    cq = {
        "id": "cbq1",
        "data": f"dl:{token}:audio",
        "message": {"chat": {"id": 999}, "message_id": 42},
    }

    async def _run():
        await bot._handle_callback(cq)
        tasks = list(bot._tracking)
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(_run())

    assert token not in bot._pending  # consumed
    with Session(engine) as session:
        jobs = session.exec(select(Job).where(Job.url == "https://example.com/watch?v=2")).all()
    assert len(jobs) == 1
    assert jobs[0].audio_only is True
    assert jobs[0].title == "Confirmed Song"


def test_callback_expired_token_is_a_noop(monkeypatch):
    bot = TelegramBot()
    cq = {
        "id": "cbq2",
        "data": "dl:missing:video",
        "message": {"chat": {"id": 999}, "message_id": 42},
    }
    asyncio.run(bot._handle_callback(cq))  # should not raise despite no real HTTP client
    with Session(engine) as session:
        assert session.exec(select(Job)).all() == []


# ---------- GET /api/telegram/status ----------
def test_telegram_status_reflects_config_and_settings(client):
    resp = client.get("/api/telegram/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] == bool(config.telegram_bot_token)
    assert data["enabled"] is False  # AppSettings default
    assert data["connected"] is False  # bot lifespan is not started in tests


# ---------- PUT /api/settings validation ----------
def test_update_settings_accepts_and_normalizes_chat_ids(client):
    resp = client.put("/api/settings", json={"telegram_allowed_chat_ids": " 123 , 456 "})
    assert resp.status_code == 200
    assert resp.json()["telegram_allowed_chat_ids"] == "123,456"


def test_update_settings_rejects_non_numeric_chat_id(client):
    resp = client.put("/api/settings", json={"telegram_allowed_chat_ids": "123,abc"})
    assert resp.status_code == 400


def test_update_settings_toggles_telegram_enabled(client):
    resp = client.put("/api/settings", json={"telegram_enabled": True})
    assert resp.status_code == 200
    assert resp.json()["telegram_enabled"] is True

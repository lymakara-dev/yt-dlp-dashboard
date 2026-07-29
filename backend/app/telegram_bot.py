"""Telegram bot: control the dashboard from a chat.

Long-polls the Telegram Bot API over httpx (same style as the LRCLIB client in
lyrics.py — no bot framework dependency). Runs as a single background task with
the same start()/stop() lifecycle shape as automation.py's Watcher.

Flow: send a link -> bot probes it and offers Video/Audio buttons -> confirming
creates a Job through the same `jobs.build_job()` the REST API uses -> the bot
edits its status message as progress events arrive on the broker -> the
finished file is uploaded back (or, past Telegram's 50MB bot upload limit, the
bot points you at the dashboard instead).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .broker import broker
from .config import config
from .db import get_settings, session_scope
from .downloader import ProbeError, probe
from .jobs import build_job
from .models import ACTIVE_STATES, Job, JobStatus
from .queue import manager

log = logging.getLogger("ytdlp-dashboard.telegram")

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # Telegram bot API document upload cap
_PENDING_TTL_S = 15 * 60  # how long an unconfirmed video/audio prompt stays valid
_PROGRESS_EDIT_INTERVAL_S = 4.0  # throttle editMessageText to stay under rate limits

_HELP_TEXT = (
    "Send me a video/audio link and I'll ask whether you want video or audio, "
    "then queue it.\n\n"
    "Commands:\n"
    "/queue — active downloads\n"
    "/status <id> — one job's status\n"
    "/cancel <id> — cancel a job\n"
    "/help — this message"
)


@dataclass
class PendingRequest:
    url: str
    chat_id: int
    created_at: float


def _parse_chat_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            ids.add(int(piece))
        except ValueError:
            continue
    return ids


def _is_allowed(chat_id: int, allowed_raw: str) -> bool:
    """Empty allowlist means deny everyone — a bot must be explicitly opened up."""
    return chat_id in _parse_chat_ids(allowed_raw)


def _format_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _format_duration(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _format_progress_line(payload: dict[str, Any]) -> str | None:
    progress = payload.get("progress")
    if progress is None:
        return None
    parts = [f"⬇️ {progress:.0f}%"]
    speed = payload.get("speed")
    if speed:
        parts.append(f"{_format_bytes(speed)}/s")
    eta = payload.get("eta")
    if eta is not None:
        parts.append(f"ETA {int(eta)}s")
    return " · ".join(parts)


class TelegramBot:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._task: asyncio.Task | None = None
        self._offset = 0
        self._pending: dict[str, PendingRequest] = {}
        self._tracking: set[asyncio.Task] = set()
        self.bot_username: str | None = None

    # ---------- lifecycle ----------
    @property
    def is_polling(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self._task is not None:
            return
        if not config.telegram_bot_token:
            log.info("Telegram bot disabled (YTDLP_TELEGRAM_BOT_TOKEN not set)")
            return
        self._client = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{config.telegram_bot_token}/",
            timeout=httpx.Timeout(35.0, connect=10.0),
        )
        try:
            me = await self._call("getMe")
            self.bot_username = me.get("username")
            log.info("Telegram bot connected as @%s", self.bot_username)
        except Exception:
            log.exception("Telegram getMe failed; the poll loop will keep retrying")
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        for t in list(self._tracking):
            t.cancel()
        self._tracking.clear()
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ---------- Telegram HTTP plumbing ----------
    async def _call(self, method: str, **params: Any) -> Any:
        assert self._client is not None
        resp = await self._client.post(method, json=params)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error on {method}: {data.get('description')}")
        return data["result"]

    async def _send_message(
        self, chat_id: int, text: str, reply_markup: dict | None = None
    ) -> dict:
        params: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            params["reply_markup"] = reply_markup
        return await self._call("sendMessage", **params)

    async def _edit_message(self, chat_id: int, message_id: int, text: str) -> None:
        try:
            await self._call("editMessageText", chat_id=chat_id, message_id=message_id, text=text)
        except Exception:
            pass  # "message is not modified" and similar are harmless

    async def _answer_callback(self, callback_query_id: str, text: str | None = None) -> None:
        params: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            params["text"] = text
        try:
            await self._call("answerCallbackQuery", **params)
        except Exception:
            pass

    async def _send_document(self, chat_id: int, filepath: str, caption: str | None = None) -> None:
        assert self._client is not None
        data = await asyncio.to_thread(Path(filepath).read_bytes)
        files = {"document": (os.path.basename(filepath), data)}
        form: dict[str, Any] = {"chat_id": str(chat_id)}
        if caption:
            form["caption"] = caption[:1024]
        resp = await self._client.post(
            "sendDocument", data=form, files=files, timeout=httpx.Timeout(120.0, connect=10.0)
        )
        resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise RuntimeError(f"sendDocument failed: {result.get('description')}")

    # ---------- poll loop ----------
    async def _loop(self) -> None:
        while True:
            try:
                with session_scope() as session:
                    enabled = get_settings(session).telegram_enabled
                if not enabled:
                    await asyncio.sleep(5)
                    continue
                updates = await self._call(
                    "getUpdates",
                    offset=self._offset,
                    timeout=25,
                    allowed_updates=["message", "callback_query"],
                )
                for upd in updates:
                    self._offset = upd["update_id"] + 1
                    try:
                        await self._handle_update(upd)
                    except Exception:
                        log.exception("Failed handling Telegram update %s", upd.get("update_id"))
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Telegram poll tick failed")
                await asyncio.sleep(5)

    async def _handle_update(self, update: dict) -> None:
        if "message" in update:
            await self._handle_message(update["message"])
        elif "callback_query" in update:
            await self._handle_callback(update["callback_query"])

    # ---------- message dispatch ----------
    async def _handle_message(self, msg: dict) -> None:
        chat_id = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()
        if not text:
            return

        with session_scope() as session:
            allowed_raw = get_settings(session).telegram_allowed_chat_ids

        if not _is_allowed(chat_id, allowed_raw):
            await self._send_message(
                chat_id,
                f"This bot is locked down.\nYour chat ID is {chat_id}.\n"
                "Ask the dashboard admin to add it under Settings → Telegram Bot.",
            )
            return

        if text.startswith("/start") or text.startswith("/help"):
            await self._send_message(chat_id, _HELP_TEXT)
        elif text.startswith("/queue"):
            await self._cmd_queue(chat_id)
        elif text.startswith("/cancel"):
            await self._cmd_cancel(chat_id, text)
        elif text.startswith("/status"):
            await self._cmd_status(chat_id, text)
        elif text.startswith(("http://", "https://")):
            await self._handle_url(chat_id, text)
        else:
            await self._send_message(chat_id, "Send me a link to download, or /help for commands.")

    async def _cmd_queue(self, chat_id: int) -> None:
        with session_scope() as session:
            jobs = (
                session.query(Job)
                .filter(Job.status.in_(ACTIVE_STATES))
                .order_by(Job.queue_position, Job.created_at)
                .all()
            )
            lines = [
                f"#{j.id} · {j.status.value} · {j.progress:.0f}% · {j.title or j.url}"
                for j in jobs
            ]
        await self._send_message(chat_id, "\n".join(lines) if lines else "Queue is empty.")

    async def _cmd_cancel(self, chat_id: int, text: str) -> None:
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            await self._send_message(chat_id, "Usage: /cancel <job id>")
            return
        job_id = int(parts[1].strip())
        ok = manager.cancel(job_id)
        msg = f"Cancelled job #{job_id}." if ok else f"Job #{job_id} not found or already finished."
        await self._send_message(chat_id, msg)

    async def _cmd_status(self, chat_id: int, text: str) -> None:
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            await self._send_message(chat_id, "Usage: /status <job id>")
            return
        job_id = int(parts[1].strip())
        with session_scope() as session:
            job = session.get(Job, job_id)
            if job is None:
                await self._send_message(chat_id, f"Job #{job_id} not found.")
                return
            lines = [f"#{job.id} · {job.status.value} · {job.progress:.0f}%", job.title or job.url]
            if job.error_message:
                lines.append(f"Error: {job.error_message}")
        await self._send_message(chat_id, "\n".join(lines))

    def _prune_pending(self) -> None:
        cutoff = time.monotonic() - _PENDING_TTL_S
        for token in [k for k, v in self._pending.items() if v.created_at < cutoff]:
            self._pending.pop(token, None)

    async def _handle_url(self, chat_id: int, url: str) -> None:
        try:
            info = await asyncio.to_thread(probe, url)
        except ProbeError as exc:
            await self._send_message(chat_id, f"Couldn't read that link: {exc}")
            return

        self._prune_pending()
        token = uuid.uuid4().hex[:12]
        self._pending[token] = PendingRequest(url=url, chat_id=chat_id, created_at=time.monotonic())

        title = info.title or url
        meta_parts = [p for p in (info.uploader, _format_duration(info.duration) if info.duration else None) if p]
        caption = title + ("\n" + " · ".join(meta_parts) if meta_parts else "")

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🎬 Video (best)", "callback_data": f"dl:{token}:video"},
                    {"text": "🎵 Audio only", "callback_data": f"dl:{token}:audio"},
                ],
                [{"text": "❌ Cancel", "callback_data": f"dl:{token}:x"}],
            ]
        }
        await self._send_message(chat_id, caption, reply_markup=keyboard)

    # ---------- callback (button) dispatch ----------
    async def _handle_callback(self, cq: dict) -> None:
        data = cq.get("data") or ""
        chat_id = cq["message"]["chat"]["id"]
        message_id = cq["message"]["message_id"]
        callback_id = cq["id"]

        with session_scope() as session:
            allowed_raw = get_settings(session).telegram_allowed_chat_ids
        if not _is_allowed(chat_id, allowed_raw):
            await self._answer_callback(callback_id, "Not authorized.")
            return

        if not data.startswith("dl:"):
            await self._answer_callback(callback_id)
            return

        _, token, mode = data.split(":", 2)
        pending = self._pending.pop(token, None)
        if pending is None:
            await self._answer_callback(callback_id, "This request expired.")
            return

        if mode == "x":
            await self._answer_callback(callback_id, "Cancelled.")
            await self._edit_message(chat_id, message_id, "❌ Cancelled.")
            return

        await self._answer_callback(callback_id, "Queued…")
        with session_scope() as session:
            job = await build_job(session, pending.url, audio_only=(mode == "audio"))
            job_id, job_title = job.id, job.title  # read before the session closes below
        await manager.enqueue(job_id)
        await self._edit_message(
            chat_id, message_id, f"⏳ Queued as job #{job_id} — {job_title or pending.url}"
        )

        task = asyncio.create_task(self._track_progress(chat_id, message_id, job_id))
        self._tracking.add(task)
        task.add_done_callback(self._tracking.discard)

    # ---------- progress tracking ----------
    async def _track_progress(self, chat_id: int, message_id: int, job_id: int) -> None:
        q = broker.subscribe(job_id)
        last_edit = 0.0
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=30)
                except asyncio.TimeoutError:
                    continue
                status = payload.get("status")
                if status in ("completed", "error", "cancelled"):
                    await self._finish_job_message(chat_id, message_id, job_id)
                    return
                now = time.monotonic()
                if now - last_edit >= _PROGRESS_EDIT_INTERVAL_S:
                    line = _format_progress_line(payload)
                    if line:
                        last_edit = now
                        await self._edit_message(chat_id, message_id, line)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Progress tracking failed for job %s", job_id)
        finally:
            broker.unsubscribe(job_id, q)

    async def _finish_job_message(self, chat_id: int, message_id: int, job_id: int) -> None:
        with session_scope() as session:
            job = session.get(Job, job_id)
            status = job.status if job else None
            title = job.title if job else None
            filepath = job.filepath if job else None
            filesize = job.filesize if job else None
            error_message = job.error_message if job else None

        if status == JobStatus.completed and filepath and os.path.exists(filepath):
            if filesize and filesize > _MAX_UPLOAD_BYTES:
                await self._edit_message(
                    chat_id,
                    message_id,
                    f"✅ Done: {title or os.path.basename(filepath)}\n"
                    f"File is {_format_bytes(filesize)}, over Telegram's 50MB bot upload "
                    "limit — grab it from the dashboard.",
                )
                return
            await self._edit_message(
                chat_id, message_id, f"✅ Done: {title or 'download complete'} — sending file…"
            )
            try:
                await self._send_document(chat_id, filepath, caption=title)
            except Exception:
                log.exception("Failed to send finished file for job %s", job_id)
                await self._send_message(
                    chat_id, "Finished, but I couldn't upload the file. Grab it from the dashboard."
                )
        elif status == JobStatus.error:
            await self._edit_message(chat_id, message_id, f"❌ Failed: {error_message or 'unknown error'}")
        elif status == JobStatus.cancelled:
            await self._edit_message(chat_id, message_id, "🚫 Cancelled.")
        else:
            await self._edit_message(chat_id, message_id, "Job finished.")


telegram_bot = TelegramBot()

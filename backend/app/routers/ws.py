"""WebSocket endpoint streaming live progress for a single job."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..broker import broker
from ..db import session_scope
from ..models import TERMINAL_STATES, Job, JobStatus
from ..queue import _snapshot

log = logging.getLogger("ytdlp-dashboard.ws")

router = APIRouter(tags=["ws"])


@router.websocket("/ws/downloads/{job_id}")
async def ws_downloads(websocket: WebSocket, job_id: int) -> None:
    await websocket.accept()

    # Send current persisted state immediately so a late subscriber is in sync.
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            await websocket.send_json({"kind": "error", "detail": "Job not found."})
            await websocket.close()
            return
        already_terminal = job.status in TERMINAL_STATES
        await websocket.send_json(_snapshot(job))

    if already_terminal:
        await websocket.close()
        return

    queue = broker.subscribe(job_id)
    try:
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=30)
            except asyncio.TimeoutError:
                # Keep-alive ping so idle connections aren't dropped by proxies.
                await websocket.send_json({"kind": "ping"})
                continue
            await websocket.send_json(msg)
            status = msg.get("status")
            if msg.get("kind") == "state" and status in {
                JobStatus.completed.value,
                JobStatus.error.value,
                JobStatus.cancelled.value,
            }:
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("WebSocket error for job %s", job_id)
    finally:
        broker.unsubscribe(job_id, queue)
        try:
            await websocket.close()
        except Exception:
            pass

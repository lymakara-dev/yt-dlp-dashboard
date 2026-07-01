"""In-process pub/sub for per-job progress events.

Worker threads publish normalized progress dicts; async consumers (the
WebSocket endpoint, console logger) subscribe per job id. Publishing is made
thread-safe via the captured event loop so the blocking download thread can
push updates without touching asyncio objects directly.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

log = logging.getLogger("ytdlp-dashboard.broker")


class ProgressBroker:
    def __init__(self) -> None:
        self._subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None
        # Last message per job so a late WS subscriber gets immediate state.
        self._last: dict[int, dict] = {}

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, job_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers[job_id].add(q)
        last = self._last.get(job_id)
        if last is not None:
            q.put_nowait(last)
        return q

    def unsubscribe(self, job_id: int, q: asyncio.Queue) -> None:
        subs = self._subscribers.get(job_id)
        if subs:
            subs.discard(q)
            if not subs:
                self._subscribers.pop(job_id, None)

    async def publish(self, job_id: int, message: dict) -> None:
        self._last[job_id] = message
        for q in list(self._subscribers.get(job_id, ())):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                # Drop the oldest update to keep the stream live.
                try:
                    q.get_nowait()
                    q.put_nowait(message)
                except Exception:
                    pass

    def publish_threadsafe(self, job_id: int, message: dict) -> None:
        """Safe to call from a worker thread."""
        if self._loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(self.publish(job_id, message), self._loop)
        except RuntimeError:
            pass


broker = ProgressBroker()

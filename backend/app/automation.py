"""Background automation: watch a folder for *.txt URL lists and auto-queue.

A single async loop polls the configured watch folder on an interval. Each
*.txt file is read (one URL per line, `#` comments ignored), a job is created
and enqueued per URL, and the file is renamed to `*.imported` so it is only
processed once. Enabled by setting a watch folder in Settings; a blank folder
disables the loop's work (it keeps sleeping cheaply).
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from .db import get_settings, session_scope
from .models import Job, JobStatus
from .queue import manager

log = logging.getLogger("ytdlp-dashboard.automation")


def _read_urls(path: str) -> list[str]:
    urls: list[str] = []
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


async def _scan_once(folder: str, default_template: str) -> None:
    if not folder or not os.path.isdir(folder):
        return
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".txt"):
            continue
        path = os.path.join(folder, name)
        try:
            urls = _read_urls(path)
        except OSError:
            continue
        ids: list[int] = []
        if urls:
            with session_scope() as session:
                jobs = [
                    Job(
                        url=u,
                        status=JobStatus.queued,
                        output_template=default_template,
                    )
                    for u in urls
                ]
                session.add_all(jobs)
                session.commit()
                for job in jobs:
                    session.refresh(job)
                    ids.append(job.id)
        for jid in ids:
            await manager.enqueue(jid)
        # Mark the file processed so it isn't imported again.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        try:
            os.rename(path, f"{path}.{stamp}.imported")
        except OSError:
            pass
        if ids:
            log.info("Watch folder imported %d URL(s) from %s", len(ids), name)


class Watcher:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while True:
            interval = 30
            try:
                with session_scope() as session:
                    settings = get_settings(session)
                    folder = settings.watch_folder
                    interval = settings.watch_interval or 30
                    template = settings.default_output_template
                await _scan_once(folder, template)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Watch folder scan failed")
            await asyncio.sleep(max(5, interval))


watcher = Watcher()

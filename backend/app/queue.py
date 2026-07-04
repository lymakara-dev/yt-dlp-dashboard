"""Async job queue + worker pool.

Jobs are enqueued by id; a configurable number of worker tasks pull ids and
run the blocking yt-dlp download in a thread executor, forwarding progress to
the broker and persisting state transitions to SQLite. Job rows survive
restarts; interrupted jobs are re-queued on startup.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from .broker import broker
from sqlmodel import func

from .db import get_settings, session_scope
from .downloader import (
    DownloadCancelled,
    DownloadFailed,
    run_download,
)
from .models import TERMINAL_STATES, Job, JobStatus, utcnow
from .options import merge_legacy

log = logging.getLogger("ytdlp-dashboard.queue")

# Minimum seconds between persisted progress writes per job (DB throttle).
_DB_THROTTLE_S = 0.5


class JobManager:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._cancel_events: dict[int, threading.Event] = {}
        self._cancel_requested: set[int] = set()
        self._last_db_write: dict[int, float] = {}
        self._started = False
        self._target_workers = 1
        self._loop: asyncio.AbstractEventLoop | None = None

    # ---------- lifecycle ----------
    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        loop = asyncio.get_running_loop()
        self._loop = loop
        broker.bind_loop(loop)

        with session_scope() as session:
            settings = get_settings(session)
            self._target_workers = max(1, settings.max_concurrency)
            # Recover interrupted jobs, preserving their prior order.
            interrupted = (
                session.query(Job)
                .filter(
                    Job.status.in_(
                        [JobStatus.queued, JobStatus.downloading, JobStatus.post_processing]
                    )
                )
                .order_by(Job.queue_position, Job.created_at)
                .all()
            )
            requeue_ids = []
            for pos, job in enumerate(interrupted, start=1):
                job.status = JobStatus.queued
                job.progress = 0.0
                job.queue_position = pos
                job.updated_at = utcnow()
                requeue_ids.append(job.id)

        for jid in requeue_ids:
            await self._queue.put(jid)
        if requeue_ids:
            log.info("Re-queued %d interrupted job(s) after restart", len(requeue_ids))

        self._scale_workers(self._target_workers)
        log.info("Job manager started with %d worker(s)", self._target_workers)

    async def shutdown(self) -> None:
        for t in self._workers:
            t.cancel()
        self._workers.clear()
        self._started = False

    def _scale_workers(self, n: int) -> None:
        n = max(1, n)
        while len(self._workers) < n:
            self._workers.append(asyncio.create_task(self._worker(len(self._workers))))
        while len(self._workers) > n:
            self._workers.pop().cancel()
        self._target_workers = n

    def set_concurrency(self, n: int) -> None:
        """Thread-safe: may be called from a sync request handler thread."""
        if not self._started or self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._scale_workers, max(1, n))

    # ---------- enqueue / cancel ----------
    async def enqueue(self, job_id: int) -> None:
        self._cancel_requested.discard(job_id)
        self._assign_position(job_id)
        # The queued item is only a wake token; real order lives in queue_position.
        await self._queue.put(job_id)

    def _assign_position(self, job_id: int) -> None:
        """Append the job to the end of the pending order (max position + 1)."""
        with session_scope() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            max_pos = (
                session.query(func.max(Job.queue_position))
                .filter(Job.status == JobStatus.queued)
                .scalar()
                or 0
            )
            job.queue_position = max_pos + 1
            job.updated_at = utcnow()

    def cancel(self, job_id: int) -> bool:
        """Request cancellation. Returns True if the job was active/queued."""
        self._cancel_requested.add(job_id)
        ev = self._cancel_events.get(job_id)
        if ev is not None:
            ev.set()
            return True
        # Queued but not yet running: mark cancelled now; worker will skip it.
        with session_scope() as session:
            job = session.get(Job, job_id)
            if job and job.status not in TERMINAL_STATES:
                job.status = JobStatus.cancelled
                job.updated_at = utcnow()
                job.finished_at = utcnow()
                broker.publish_threadsafe(job_id, _snapshot(job))
                return True
        return False

    # ---------- worker ----------
    def _claim_next(self) -> int | None:
        """Pick the next queued job by position and mark it downloading.

        Runs synchronously on the event loop, so there is no await between the
        read and the status write: two workers cannot claim the same job, and
        no explicit lock is needed.
        """
        with session_scope() as session:
            job = (
                session.query(Job)
                .filter(Job.status == JobStatus.queued)
                .order_by(Job.queue_position, Job.created_at)
                .first()
            )
            if job is None:
                return None
            job.status = JobStatus.downloading
            job.updated_at = utcnow()
            return job.id

    async def _worker(self, idx: int) -> None:
        while True:
            await self._queue.get()  # wake token; may be stale (orphaned by a cancel)
            try:
                job_id = self._claim_next()
                if job_id is None:
                    continue  # nothing queued right now
                await self._process(job_id)
            except asyncio.CancelledError:
                raise
            except Exception:  # never let a worker die
                log.exception("Worker %d failed processing a job", idx)
            finally:
                self._queue.task_done()

    async def _process(self, job_id: int) -> None:
        # Load options snapshot.
        with session_scope() as session:
            job = session.get(Job, job_id)
            if job is None or job.status in TERMINAL_STATES:
                return
            settings = get_settings(session)
            options = merge_legacy(
                format_id=job.format_id,
                quality_preset=job.quality_preset,
                audio_only=job.audio_only,
                subtitles=job.subtitles,
                embed_thumbnail=job.embed_thumbnail,
                sponsorblock=job.sponsorblock,
                options=job.options,
            )
            opts = {
                "url": job.url,
                "download_dir": settings.download_dir,
                "output_template": job.output_template or settings.default_output_template,
                "options": options,
            }
            job.status = JobStatus.downloading
            job.updated_at = utcnow()
            snapshot = _snapshot(job)
        await broker.publish(job_id, snapshot)

        cancel_event = threading.Event()
        self._cancel_events[job_id] = cancel_event
        if job_id in self._cancel_requested:
            cancel_event.set()

        on_event = self._make_on_event(job_id)

        try:
            result = await asyncio.to_thread(
                run_download,
                on_event=on_event,
                is_cancelled=cancel_event.is_set,
                **opts,
            )
        except DownloadCancelled:
            self._finalize(job_id, JobStatus.cancelled)
        except DownloadFailed as exc:
            self._finalize(job_id, JobStatus.error, error_message=str(exc))
        except Exception as exc:  # unexpected
            log.exception("Unexpected error for job %s", job_id)
            self._finalize(job_id, JobStatus.error, error_message=str(exc))
        else:
            self._finalize(job_id, JobStatus.completed, result=result)
        finally:
            self._cancel_events.pop(job_id, None)
            self._cancel_requested.discard(job_id)
            self._last_db_write.pop(job_id, None)

    # ---------- progress callback (runs in worker thread) ----------
    def _make_on_event(self, job_id: int):
        def on_event(payload: dict[str, Any]) -> None:
            now = time.monotonic()
            kind = payload.get("kind")
            new_status: JobStatus | None = None
            if kind == "postprocess" and payload.get("status") in ("started", "processing"):
                new_status = JobStatus.post_processing

            # Throttle DB writes (always write on status change).
            last = self._last_db_write.get(job_id, 0.0)
            should_write = new_status is not None or (now - last) >= _DB_THROTTLE_S

            published: dict[str, Any] | None = None
            if should_write:
                self._last_db_write[job_id] = now
                with session_scope() as session:
                    job = session.get(Job, job_id)
                    if job is None:
                        return
                    if new_status is not None:
                        job.status = new_status
                        if new_status == JobStatus.post_processing:
                            # Download bytes are done; keep the bar full.
                            job.progress = 100.0
                            job.speed = None
                            job.eta = None
                    if kind == "progress":
                        if payload.get("progress") is not None:
                            job.progress = payload["progress"]
                        job.downloaded_bytes = payload.get("downloaded_bytes")
                        job.total_bytes = payload.get("total_bytes")
                        job.speed = payload.get("speed")
                        job.eta = payload.get("eta")
                    job.updated_at = utcnow()
                    published = _snapshot(job)
            if published is None:
                # Lightweight live update without a DB round-trip.
                published = {"id": job_id, **payload}
            broker.publish_threadsafe(job_id, published)

        return on_event

    def _finalize(
        self,
        job_id: int,
        status: JobStatus,
        *,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.status = status
            job.updated_at = utcnow()
            job.finished_at = utcnow()
            if status == JobStatus.completed and result:
                job.progress = 100.0
                job.filepath = result.get("filepath")
                job.filesize = result.get("filesize")
                job.title = job.title or result.get("title")
                job.uploader = job.uploader or result.get("uploader")
                job.duration = job.duration or result.get("duration")
                job.thumbnail = job.thumbnail or result.get("thumbnail")
                job.ext = result.get("ext")
            if error_message:
                job.error_message = error_message
            snapshot = _snapshot(job)
        broker.publish_threadsafe(job_id, snapshot)


def _snapshot(job: Job) -> dict[str, Any]:
    """Full job state for WS subscribers."""
    return {
        "id": job.id,
        "kind": "state",
        "status": job.status.value if isinstance(job.status, JobStatus) else job.status,
        "progress": job.progress,
        "downloaded_bytes": job.downloaded_bytes,
        "total_bytes": job.total_bytes,
        "speed": job.speed,
        "eta": job.eta,
        "title": job.title,
        "filepath": job.filepath,
        "filesize": job.filesize,
        "error_message": job.error_message,
    }


manager = JobManager()

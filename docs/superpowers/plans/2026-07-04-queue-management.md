# Queue Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated, reorderable Queue page that shows every pending/active download with live progress and lets the user cancel one, several, or all queued jobs.

**Architecture:** Add a persistent `queue_position` column to `Job`. The in-memory `asyncio.Queue` becomes an opaque wake-token signal; the actual pick order comes from the DB. A worker wakes on a token and synchronously claims the next `queued` job ordered by `queue_position`, marking it `downloading` so no two workers grab the same one. Reordering is a plain DB update via a new `POST /api/downloads/reorder` endpoint; bulk cancel via `POST /api/downloads/cancel`. The frontend gains a `Queue` nav tab with grouped sections, native HTML5 drag-and-drop plus move buttons, and multi-select cancel.

**Tech Stack:** Backend — FastAPI, SQLModel/SQLAlchemy, SQLite, pytest (run via `uv`). Frontend — React 19, TanStack Query, Tailwind, lucide-react, sonner (no new dependencies).

## Global Constraints

- Backend tests run with: `cd backend && uv run python -m pytest -q` (must stay green; currently 52 pass).
- Frontend typecheck: `cd frontend && pnpm lint` (`tsc --noEmit`). Frontend build: `cd frontend && pnpm build`. **No frontend test runner exists** — frontend tasks are verified by typecheck + build + manual run.
- **No new frontend dependencies.** Drag-and-drop uses native HTML5 DnD.
- `queue_position` is only meaningful for `queued` jobs. Positions are consecutive integers starting at 1; the UI badge shows this value directly.
- Reorder/bulk-cancel endpoints **skip** ids that are unknown or no longer `queued`/cancelable — never 500 or 422 on them (consistent with each other).
- TypeScript types in `frontend/src/lib/types.ts` are the hand-written mirror of `backend/app/schemas.py` — keep them in sync.
- Follow existing code style: `from __future__ import annotations`, module-level `log`, sonner `toast.error` for mutation failures, `@/` import alias on the frontend.

---

### Task 1: Add `queue_position` to the Job model, migration, and API contract

**Files:**
- Modify: `backend/app/models.py` (Job fields, near `created_at`)
- Modify: `backend/app/db.py:17-22` (`_MIGRATIONS` list)
- Modify: `backend/app/schemas.py` (`JobRead`)
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `Job.queue_position: int` (SQLModel column, default 0, indexed). `JobRead.queue_position: int`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_api.py`:

```python
def test_jobread_exposes_queue_position():
    from app.models import Job, JobStatus
    from app.schemas import JobRead

    job = Job(url="https://x", status=JobStatus.queued, queue_position=3)
    read = JobRead.model_validate(job)
    assert read.queue_position == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/test_api.py::test_jobread_exposes_queue_position -q`
Expected: FAIL — `Job(... queue_position=3)` raises `TypeError` (unexpected keyword) or `JobRead` has no such field.

- [ ] **Step 3: Add the model field**

In `backend/app/models.py`, inside `class Job`, add immediately after the `output_template: str | None = None` line (end of the "Requested options" block):

```python
    # Ordering within the pending queue; lower runs first. Only meaningful while
    # status == queued. Assigned on enqueue, rewritten by the reorder endpoint.
    queue_position: int = Field(default=0, index=True)
```

- [ ] **Step 4: Add the additive migration**

In `backend/app/db.py`, add to the `_MIGRATIONS` list (after the `scheduled_at` entry):

```python
    ("job", "queue_position", "INTEGER NOT NULL DEFAULT 0"),
```

- [ ] **Step 5: Expose it in the API contract**

In `backend/app/schemas.py`, inside `class JobRead`, add after the `output_template: str | None = None` line:

```python
    queue_position: int = 0
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_api.py -q`
Expected: PASS (all tests in file).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/db.py backend/app/schemas.py backend/tests/test_api.py
git commit -m "feat(queue): add queue_position to Job model and API contract"
```

---

### Task 2: DB-ordered enqueue + claim in the worker pool

**Files:**
- Modify: `backend/app/queue.py` (imports, `enqueue`, new `_assign_position`, new `_claim_next`, `_worker`, `start`)
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_queue.py`

**Interfaces:**
- Consumes: `Job.queue_position` (Task 1).
- Produces:
  - `JobManager.enqueue(job_id: int)` — assigns `queue_position = max(queued)+1`, then pushes a wake token.
  - `JobManager._claim_next() -> int | None` — synchronously claims the next `queued` job by `(queue_position, created_at)`, marks it `downloading`, returns its id (or `None` if no queued job).
  - `backend/tests/conftest.py` — points the DB at a temp file (env `YTDLP_DATABASE_URL`) and provides an autouse `clean_db` fixture plus a `client` fixture (used by Tasks 3–4).

- [ ] **Step 1: Write the test harness (conftest)**

Create `backend/tests/conftest.py`. The env var MUST be set before any `app.*` import so `app.config.Config()` reads it:

```python
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
```

- [ ] **Step 2: Write the failing test for enqueue + claim ordering**

Create `backend/tests/test_queue.py`:

```python
"""Queue ordering: enqueue assigns positions, claim pops in position order."""
from __future__ import annotations

import asyncio

from app.db import engine
from app.models import Job, JobStatus
from app.queue import JobManager
from sqlmodel import Session


def _make_queued(*urls: str) -> list[int]:
    ids: list[int] = []
    with Session(engine) as s:
        jobs = [Job(url=u, status=JobStatus.queued) for u in urls]
        s.add_all(jobs)
        s.commit()
        for j in jobs:
            s.refresh(j)
            ids.append(j.id)
    return ids


def test_enqueue_assigns_sequential_positions():
    a, b, c = _make_queued("a", "b", "c")
    mgr = JobManager()

    async def _run():
        for jid in (a, b, c):
            await mgr.enqueue(jid)

    asyncio.run(_run())

    with Session(engine) as s:
        assert [s.get(Job, i).queue_position for i in (a, b, c)] == [1, 2, 3]


def test_claim_next_pops_in_position_order():
    a, b, c = _make_queued("a", "b", "c")
    mgr = JobManager()
    asyncio.run(_enqueue_all(mgr, [a, b, c]))

    # Give c the lowest position so it must be claimed first.
    with Session(engine) as s:
        s.get(Job, c).queue_position = 0
        s.commit()

    assert mgr._claim_next() == c
    assert mgr._claim_next() == a
    assert mgr._claim_next() == b
    assert mgr._claim_next() is None  # all claimed


def test_claim_next_marks_downloading():
    (a,) = (_make_queued("a")[0],)
    mgr = JobManager()
    asyncio.run(mgr.enqueue(a))
    assert mgr._claim_next() == a
    with Session(engine) as s:
        assert s.get(Job, a).status == JobStatus.downloading


async def _enqueue_all(mgr: JobManager, ids: list[int]) -> None:
    for jid in ids:
        await mgr.enqueue(jid)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && uv run python -m pytest tests/test_queue.py -q`
Expected: FAIL — `JobManager` has no `_claim_next`; `enqueue` does not set `queue_position` (positions stay 0).

- [ ] **Step 4: Add the `func` import**

In `backend/app/queue.py`, add below `from .broker import broker`:

```python
from sqlmodel import func
```

- [ ] **Step 5: Implement position assignment in `enqueue`**

In `backend/app/queue.py`, replace the existing `enqueue` method:

```python
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
```

- [ ] **Step 6: Implement `_claim_next`**

In `backend/app/queue.py`, add this method just above `_worker`:

```python
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
```

- [ ] **Step 7: Rewrite the worker loop to claim by position**

In `backend/app/queue.py`, replace the body of `_worker`:

```python
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
```

- [ ] **Step 8: Make startup recovery preserve order and push tokens**

In `backend/app/queue.py`, inside `start()`, replace the interrupted-job recovery block (the `interrupted = session.query(...)` loop that builds `requeue_ids`) with:

```python
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
```

(The `for jid in requeue_ids: await self._queue.put(jid)` block that follows stays unchanged — it pushes one wake token per recovered job.)

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_queue.py -q`
Expected: PASS (3 tests).

- [ ] **Step 10: Run the whole backend suite (no regressions)**

Run: `cd backend && uv run python -m pytest -q`
Expected: PASS (all previous tests + new ones).

- [ ] **Step 11: Commit**

```bash
git add backend/app/queue.py backend/tests/conftest.py backend/tests/test_queue.py
git commit -m "feat(queue): DB-ordered enqueue and position-based worker claim"
```

---

### Task 3: `POST /api/downloads/reorder` endpoint

**Files:**
- Modify: `backend/app/schemas.py` (add `ReorderRequest`)
- Modify: `backend/app/routers/downloads.py` (import + new route)
- Modify: `backend/tests/test_queue.py`

**Interfaces:**
- Consumes: `JobManager._claim_next` (Task 2), `client` fixture (Task 2).
- Produces: `POST /api/downloads/reorder` with body `{"ordered_ids": [int, ...]}` → `JobList` of the reordered queued jobs. Reassigns `queue_position` to 1..n over currently-`queued` jobs; unknown/non-queued ids are skipped; queued jobs omitted from `ordered_ids` keep relative order and sort after the listed ones.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_queue.py`:

```python
def test_reorder_endpoint_rewrites_positions(client):
    a, b, c = _make_queued("a", "b", "c")
    # Seed positions 1,2,3 so there's a defined starting order.
    with Session(engine) as s:
        for pos, jid in enumerate((a, b, c), start=1):
            s.get(Job, jid).queue_position = pos
        s.commit()

    resp = client.post("/api/downloads/reorder", json={"ordered_ids": [c, a, b]})
    assert resp.status_code == 200

    with Session(engine) as s:
        assert s.get(Job, c).queue_position == 1
        assert s.get(Job, a).queue_position == 2
        assert s.get(Job, b).queue_position == 3

    body = resp.json()
    assert [item["id"] for item in body["items"]] == [c, a, b]


def test_reorder_skips_unknown_and_nonqueued_ids(client):
    a, b = _make_queued("a", "b")
    # 999999 does not exist; it must be ignored, not error.
    resp = client.post("/api/downloads/reorder", json={"ordered_ids": [b, 999999, a]})
    assert resp.status_code == 200
    with Session(engine) as s:
        assert s.get(Job, b).queue_position == 1
        assert s.get(Job, a).queue_position == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run python -m pytest tests/test_queue.py -k reorder -q`
Expected: FAIL — 404/405 (route not defined).

- [ ] **Step 3: Add the request schema**

In `backend/app/schemas.py`, add near the other download schemas (after `DeleteJobRequest`):

```python
class ReorderRequest(BaseModel):
    ordered_ids: list[int]
```

- [ ] **Step 4: Implement the endpoint**

In `backend/app/routers/downloads.py`, add `ReorderRequest` to the `from ..schemas import (...)` block, then add this route **immediately after the `create_batch` route** (before `list_downloads`, so it is matched ahead of `/{job_id}`):

```python
@router.post("/reorder", response_model=JobList)
def reorder_downloads(req: ReorderRequest, session: Session = Depends(get_session)) -> JobList:
    """Rewrite queue_position over the currently-queued jobs in the given order.

    Ids that are unknown or no longer queued are skipped. Queued jobs omitted
    from the payload keep their relative order and sort after the listed ones.
    """
    queued = session.exec(
        select(Job)
        .where(Job.status == JobStatus.queued)
        .order_by(Job.queue_position, Job.created_at)
    ).all()
    by_id = {j.id: j for j in queued}

    listed = [by_id[i] for i in req.ordered_ids if i in by_id]
    listed_ids = {j.id for j in listed}
    ordered = listed + [j for j in queued if j.id not in listed_ids]

    for pos, job in enumerate(ordered, start=1):
        job.queue_position = pos
        job.updated_at = utcnow()
    session.commit()

    items = [_job_read(j) for j in ordered]
    return JobList(items=items, total=len(items), page=1, page_size=max(1, len(items)))
```

(Note: `select`, `JobStatus`, `utcnow`, `JobList`, `_job_read` are all already imported/defined in this file.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_queue.py -k reorder -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/downloads.py backend/tests/test_queue.py
git commit -m "feat(queue): add POST /api/downloads/reorder"
```

---

### Task 4: `POST /api/downloads/cancel` bulk-cancel endpoint

**Files:**
- Modify: `backend/app/schemas.py` (add `BulkCancelRequest`, `BulkCancelResult`)
- Modify: `backend/app/routers/downloads.py` (import + new route)
- Modify: `backend/tests/test_queue.py`

**Interfaces:**
- Consumes: `manager.cancel`, `client` fixture.
- Produces: `POST /api/downloads/cancel` with body `{"ids": [int, ...]}` → `{"cancelled": int}`. Unknown or already-terminal ids are skipped (not counted).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_queue.py`:

```python
def test_bulk_cancel_cancels_queued_jobs(client):
    a, b, c = _make_queued("a", "b", "c")
    resp = client.post("/api/downloads/cancel", json={"ids": [a, b, 999999]})
    assert resp.status_code == 200
    assert resp.json()["cancelled"] == 2  # 999999 skipped

    with Session(engine) as s:
        assert s.get(Job, a).status == JobStatus.cancelled
        assert s.get(Job, b).status == JobStatus.cancelled
        assert s.get(Job, c).status == JobStatus.queued  # untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run python -m pytest tests/test_queue.py -k bulk_cancel -q`
Expected: FAIL — route not defined.

- [ ] **Step 3: Add the schemas**

In `backend/app/schemas.py`, after `ReorderRequest`:

```python
class BulkCancelRequest(BaseModel):
    ids: list[int]


class BulkCancelResult(BaseModel):
    cancelled: int
```

- [ ] **Step 4: Implement the endpoint**

In `backend/app/routers/downloads.py`, add `BulkCancelRequest, BulkCancelResult` to the `from ..schemas import (...)` block, then add this route **immediately after `reorder_downloads`**:

```python
@router.post("/cancel", response_model=BulkCancelResult)
def cancel_downloads(req: BulkCancelRequest, session: Session = Depends(get_session)) -> BulkCancelResult:
    """Cancel many jobs at once. Unknown or already-terminal ids are skipped."""
    cancelled = 0
    for jid in req.ids:
        job = session.get(Job, jid)
        if job is None or job.status in TERMINAL_STATES:
            continue
        manager.cancel(jid)
        cancelled += 1
    return BulkCancelResult(cancelled=cancelled)
```

(`TERMINAL_STATES` and `manager` are already imported in this file.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run python -m pytest tests/test_queue.py -q`
Expected: PASS (all queue tests).

- [ ] **Step 6: Full suite + commit**

```bash
cd backend && uv run python -m pytest -q
```
Expected: PASS (all).

```bash
git add backend/app/schemas.py backend/app/routers/downloads.py backend/tests/test_queue.py
git commit -m "feat(queue): add POST /api/downloads/cancel bulk cancel"
```

---

### Task 5: Frontend types + API client methods

**Files:**
- Modify: `frontend/src/lib/types.ts` (Job interface)
- Modify: `frontend/src/lib/api.ts` (two methods)

**Interfaces:**
- Consumes: backend endpoints from Tasks 1, 3, 4.
- Produces:
  - `Job.queue_position: number`.
  - `api.reorderDownloads(orderedIds: number[]) => Promise<JobList>`.
  - `api.cancelDownloads(ids: number[]) => Promise<{ cancelled: number }>`.

- [ ] **Step 1: Add `queue_position` to the Job type**

In `frontend/src/lib/types.ts`, inside `interface Job`, add after the `output_template: string | null;` line:

```typescript
  queue_position: number;
```

- [ ] **Step 2: Add the API client methods**

In `frontend/src/lib/api.ts`, add inside the `api` object after the `cancelDownload` method:

```typescript
  reorderDownloads: (orderedIds: number[]) =>
    request<JobList>("/api/downloads/reorder", {
      method: "POST",
      body: JSON.stringify({ ordered_ids: orderedIds }),
    }),

  cancelDownloads: (ids: number[]) =>
    request<{ cancelled: number }>("/api/downloads/cancel", {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),
```

(`JobList` is already imported at the top of `api.ts`.)

- [ ] **Step 3: Typecheck**

Run: `cd frontend && pnpm lint`
Expected: PASS (no type errors).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "feat(queue): frontend types and API client for reorder/bulk-cancel"
```

---

### Task 6: `QueueItem` component (reorder controls + selection around DownloadCard)

**Files:**
- Create: `frontend/src/components/QueueItem.tsx`

**Interfaces:**
- Consumes: `DownloadCard` (existing), `Job` type with `queue_position` (Task 5).
- Produces: `QueueItem` component with this exact prop contract (consumed by Task 7):

```typescript
interface QueueItemProps {
  job: Job;
  index: number;          // 0-based index within the queued list
  total: number;          // number of queued items
  onMove: (from: number, to: number) => void;
  onDragStart: (index: number) => void;
  onDragOver: (index: number) => void;
  onDrop: (index: number) => void;
  selectionMode: boolean;
  selected: boolean;
  onToggleSelect: (id: number) => void;
}
```

- [ ] **Step 1: Create the component**

Create `frontend/src/components/QueueItem.tsx`:

```tsx
import { ChevronDown, ChevronUp, ChevronsUp, GripVertical } from "lucide-react";
import { DownloadCard } from "@/components/DownloadCard";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Job } from "@/lib/types";

interface QueueItemProps {
  job: Job;
  index: number;
  total: number;
  onMove: (from: number, to: number) => void;
  onDragStart: (index: number) => void;
  onDragOver: (index: number) => void;
  onDrop: (index: number) => void;
  selectionMode: boolean;
  selected: boolean;
  onToggleSelect: (id: number) => void;
}

export function QueueItem({
  job,
  index,
  total,
  onMove,
  onDragStart,
  onDragOver,
  onDrop,
  selectionMode,
  selected,
  onToggleSelect,
}: QueueItemProps) {
  const first = index === 0;
  const last = index === total - 1;

  return (
    <div
      draggable={!selectionMode}
      onDragStart={() => onDragStart(index)}
      onDragOver={(e) => {
        e.preventDefault();
        onDragOver(index);
      }}
      onDrop={(e) => {
        e.preventDefault();
        onDrop(index);
      }}
      className={cn(
        "flex items-stretch gap-2 rounded-xl",
        selected && "ring-2 ring-primary",
        !selectionMode && "cursor-grab active:cursor-grabbing",
      )}
    >
      <div className="flex flex-col items-center justify-center gap-1 pl-1 text-muted-foreground">
        {selectionMode ? (
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelect(job.id)}
            aria-label={`Select job ${job.id}`}
            className="h-4 w-4 accent-current"
          />
        ) : (
          <>
            <GripVertical className="h-4 w-4" aria-hidden />
            <span className="text-[11px] font-semibold tabular-nums">#{index + 1}</span>
          </>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <DownloadCard job={job} />
      </div>

      {!selectionMode && (
        <div className="flex flex-col items-center justify-center gap-1 pr-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            disabled={first}
            onClick={() => onMove(index, 0)}
            title="Download next"
            aria-label="Move to top"
          >
            <ChevronsUp className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            disabled={first}
            onClick={() => onMove(index, index - 1)}
            title="Move up"
            aria-label="Move up"
          >
            <ChevronUp className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            disabled={last}
            onClick={() => onMove(index, index + 1)}
            title="Move down"
            aria-label="Move down"
          >
            <ChevronDown className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm lint`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/QueueItem.tsx
git commit -m "feat(queue): QueueItem with drag handle, move buttons, selection"
```

---

### Task 7: `QueuePage` + wire into nav, remove home Active downloads

**Files:**
- Create: `frontend/src/components/QueuePage.tsx`
- Modify: `frontend/src/components/Header.tsx` (View type + NAV entry)
- Modify: `frontend/src/App.tsx` (add queue view, drop ActiveDownloads from home)
- Delete: `frontend/src/components/ActiveDownloads.tsx`

**Interfaces:**
- Consumes: `QueueItem` (Task 6), `DownloadCard`, `api.reorderDownloads`, `api.cancelDownloads`, `api.listDownloads`.
- Produces: `QueuePage` component (default-less named export `QueuePage`); `View` union gains `"queue"`.

- [ ] **Step 1: Create the QueuePage**

Create `frontend/src/components/QueuePage.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckSquare, Inbox, Trash2, X } from "lucide-react";
import { type ReactNode, useState } from "react";
import { toast } from "sonner";
import { DownloadCard } from "@/components/DownloadCard";
import { QueueItem } from "@/components/QueueItem";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import type { Job, JobList, JobStatus } from "@/lib/types";

const RUNNING: JobStatus[] = ["downloading", "post-processing"];

export function QueuePage() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["downloads"],
    queryFn: () => api.listDownloads(1, 100),
    refetchInterval: 5000,
  });

  const jobs = data?.items ?? [];
  const running = jobs.filter((j) => RUNNING.includes(j.status));
  const scheduled = jobs.filter((j) => j.status === "scheduled");
  const queued = jobs
    .filter((j) => j.status === "queued")
    .sort((a, b) => a.queue_position - b.queue_position);

  const [selectionMode, setSelectionMode] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [dragFrom, setDragFrom] = useState<number | null>(null);

  const reorder = useMutation({
    mutationFn: (ids: number[]) => api.reorderDownloads(ids),
    // Optimistic: reflect the new order immediately so DnD feels instant.
    onMutate: async (ids: number[]) => {
      await qc.cancelQueries({ queryKey: ["downloads"] });
      const prev = qc.getQueryData<JobList>(["downloads"]);
      if (prev) {
        const pos = new Map(ids.map((id, i) => [id, i + 1]));
        qc.setQueryData<JobList>(["downloads"], {
          ...prev,
          items: prev.items.map((j) =>
            pos.has(j.id) ? { ...j, queue_position: pos.get(j.id)! } : j,
          ),
        });
      }
      return { prev };
    },
    onError: (e: ApiError, _ids, ctx) => {
      if (ctx?.prev) qc.setQueryData(["downloads"], ctx.prev);
      toast.error("Reorder failed", { description: e.message });
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["downloads"] }),
  });

  const bulkCancel = useMutation({
    mutationFn: (ids: number[]) => api.cancelDownloads(ids),
    onSuccess: (res) => {
      toast.success(`Cancelled ${res.cancelled} download${res.cancelled === 1 ? "" : "s"}`);
      setSelected(new Set());
      setSelectionMode(false);
      qc.invalidateQueries({ queryKey: ["downloads"] });
    },
    onError: (e: ApiError) => toast.error("Cancel failed", { description: e.message }),
  });

  function applyOrder(next: Job[]) {
    reorder.mutate(next.map((j) => j.id));
  }

  function move(from: number, to: number) {
    if (to < 0 || to >= queued.length || from === to) return;
    const next = [...queued];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    applyOrder(next);
  }

  function handleDrop(target: number) {
    if (dragFrom === null) return;
    move(dragFrom, target);
    setDragFrom(null);
  }

  function toggleSelect(id: number) {
    setSelected((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  const activeCount = running.length + queued.length + scheduled.length;

  if (activeCount === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed py-14 text-center text-muted-foreground">
        <Inbox className="h-6 w-6" />
        <p className="text-sm">The queue is empty. Add a download to get started.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">
          {activeCount} in queue
          {running.length > 0 && ` · ${running.length} downloading`}
        </span>
        <div className="flex items-center gap-2">
          {queued.length > 0 && !selectionMode && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => bulkCancel.mutate(queued.map((j) => j.id))}
              disabled={bulkCancel.isPending}
            >
              <Trash2 className="h-3.5 w-3.5" /> Cancel all queued
            </Button>
          )}
          {queued.length > 0 && (
            <Button
              variant={selectionMode ? "secondary" : "outline"}
              size="sm"
              onClick={() => {
                setSelectionMode((m) => !m);
                setSelected(new Set());
              }}
            >
              {selectionMode ? <X className="h-3.5 w-3.5" /> : <CheckSquare className="h-3.5 w-3.5" />}
              {selectionMode ? "Done" : "Select"}
            </Button>
          )}
        </div>
      </div>

      {/* Selection action bar */}
      {selectionMode && selected.size > 0 && (
        <div className="flex items-center justify-between rounded-lg border bg-secondary/40 px-3 py-2 text-sm">
          <span>{selected.size} selected</span>
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            onClick={() => bulkCancel.mutate([...selected])}
            disabled={bulkCancel.isPending}
          >
            <Trash2 className="h-3.5 w-3.5" /> Cancel selected
          </Button>
        </div>
      )}

      {running.length > 0 && (
        <Section title="Downloading now">
          {running.map((job) => (
            <DownloadCard key={job.id} job={job} />
          ))}
        </Section>
      )}

      {queued.length > 0 && (
        <Section title="Up next">
          {queued.map((job, i) => (
            <QueueItem
              key={job.id}
              job={job}
              index={i}
              total={queued.length}
              onMove={move}
              onDragStart={setDragFrom}
              onDragOver={() => {}}
              onDrop={handleDrop}
              selectionMode={selectionMode}
              selected={selected.has(job.id)}
              onToggleSelect={toggleSelect}
            />
          ))}
        </Section>
      )}

      {scheduled.length > 0 && (
        <Section title="Scheduled">
          {scheduled.map((job) => (
            <DownloadCard key={job.id} job={job} />
          ))}
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h2>
      <div className="space-y-3">{children}</div>
    </section>
  );
}
```

- [ ] **Step 2: Add the Queue nav entry**

In `frontend/src/components/Header.tsx`:
- Change the import line to include `ListOrdered`:
  ```typescript
  import { Download, History, ListOrdered, Search, Settings } from "lucide-react";
  ```
- Change the `View` type:
  ```typescript
  export type View = "home" | "queue" | "search" | "history" | "settings";
  ```
- Add to the `NAV` array, right after the `home` entry:
  ```typescript
  { key: "queue", label: "Queue", icon: ListOrdered },
  ```

- [ ] **Step 3: Wire QueuePage into App and remove ActiveDownloads from home**

In `frontend/src/App.tsx`:
- Remove the import line `import { ActiveDownloads } from "@/components/ActiveDownloads";`
- Add `import { QueuePage } from "@/components/QueuePage";`
- Replace the home block's contents so it no longer renders `<ActiveDownloads />`:
  ```tsx
        {view === "home" && (
          <div className="space-y-8">
            <SubmitView />
            <BatchImport />
          </div>
        )}
        {view === "queue" && (
          <div className="space-y-4">
            <h1 className="text-xl font-semibold">Queue</h1>
            <QueuePage />
          </div>
        )}
  ```
  (Insert the `queue` block immediately after the `home` block.)

- [ ] **Step 4: Delete the superseded component**

```bash
git rm frontend/src/components/ActiveDownloads.tsx
```

- [ ] **Step 5: Typecheck and build**

Run: `cd frontend && pnpm lint && pnpm build`
Expected: PASS — no type errors, build succeeds. (If `pnpm lint` flags an unused import in `App.tsx`, remove it.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/QueuePage.tsx frontend/src/components/Header.tsx frontend/src/App.tsx
git commit -m "feat(queue): dedicated Queue page with reorder and bulk cancel"
```

---

### Task 8: End-to-end verification + docs

**Files:**
- Modify: `README.md` (Features + API Reference sections)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Full backend suite**

Run: `cd backend && uv run python -m pytest -q`
Expected: PASS (all).

- [ ] **Step 2: Frontend typecheck + build**

Run: `cd frontend && pnpm lint && pnpm build`
Expected: PASS.

- [ ] **Step 3: Manual end-to-end check**

Use the `run` skill (or start backend `cd backend && uv run uvicorn app.main:app --port 8000` + `cd frontend && pnpm dev`). Verify:
- The **Queue** tab appears in the header; the home/Download view no longer shows an "Active downloads" section.
- Queue several downloads (or scheduled jobs). They appear under **Up next** with `#1, #2, …` badges; anything running shows under **Downloading now**; scheduled under **Scheduled**.
- Drag a queued card to a new spot → order updates and persists after refresh. Move-up/down and "Download next" (double-chevron) buttons reorder too.
- **Cancel all queued** empties the Up next section. **Select** mode → check several → **Cancel selected** cancels only those.
- Per-card **Cancel** still works on a downloading job.

- [ ] **Step 4: Update README**

In `README.md`, under the **Features → Downloading** bullet list, add:

```markdown
- **Queue page:** a dedicated tab lists everything pending or in progress — grouped into *Downloading now*, *Up next*, and *Scheduled* — with live progress. Reorder the waiting queue by drag-and-drop or move / "Download next" buttons, and cancel a single job, a multi-select set, or all queued at once.
```

In the **API Reference** section, add these rows to the downloads endpoint table (match the existing table's column format):

```markdown
| `POST` | `/api/downloads/reorder` | Reorder the pending queue (`{ "ordered_ids": [...] }`) |
| `POST` | `/api/downloads/cancel` | Bulk-cancel jobs (`{ "ids": [...] }`) |
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: document queue management feature and endpoints"
```

---

## Self-Review Notes

- **Spec coverage:** Dedicated Queue page (Task 7) ✓; bulk actions — cancel all + multi-select (Tasks 4, 7) ✓; reorder drag-and-drop + buttons (Tasks 2–3, 6–7) ✓; stronger UI / grouped sections (Task 7) ✓; DB-backed ordering with wake-token queue (Task 2) ✓; `queue_position` in model/migration/contract/types (Tasks 1, 5) ✓; skip-not-fatal id handling (Tasks 3, 4) ✓; remove home ActiveDownloads (Task 7) ✓; backend tests, manual frontend verification (Tasks 2–4, 8) ✓.
- **Position numbering:** consecutive from 1 everywhere (`enqueue` max+1, reorder `enumerate(..., start=1)`, recovery `enumerate(..., start=1)`, UI badge `index + 1`).
- **Type consistency:** `_claim_next`, `enqueue`, `_assign_position`, `reorderDownloads`, `cancelDownloads`, `QueueItemProps` used with identical signatures across tasks.

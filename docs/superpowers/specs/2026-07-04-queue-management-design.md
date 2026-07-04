# Queue Management — Design

**Date:** 2026-07-04
**Status:** Approved, pending implementation plan
**Branch:** feature/ytdlp-complete

## Goal

Give the user a first-class **Queue** surface: a dedicated page that lists every
pending and in-progress download with live progress, lets them **reorder** the
waiting queue, **cancel** any job (single, multi-select, or all queued), and
clearly separates what is downloading now from what is waiting.

## Context: what already exists

- The home ("Download") view has an `ActiveDownloads` section
  (`frontend/src/components/ActiveDownloads.tsx`) that lists
  `scheduled / queued / downloading / post-processing` jobs as `DownloadCard`s
  with live progress (speed, ETA, %, sparkline) and a per-job **Cancel** button.
- The backend already cancels any job (queued or in-flight) via
  `POST /api/downloads/{id}/cancel`.
- The queue (`backend/app/queue.py`) is an in-memory `asyncio.Queue` FIFO with a
  worker pool sized by `AppSettings.max_concurrency`. It has **no notion of
  position** and **cannot be reordered**.

So the raw "view + cancel" capability exists; this feature promotes it to a
dedicated, more capable surface and adds ordering + bulk actions. The largest new
piece is reordering, which requires backend changes.

## Architecture decision: reorderable queue

**Chosen approach — DB-backed ordering, in-memory queue as a wake signal.**

- Add a `queue_position` integer column to `Job`.
- Keep the existing `asyncio.Queue`, but treat the items it holds as opaque
  **wake tokens**, not the source of order. Ordering comes entirely from the DB.
- A worker wakes on a token, then — under an `asyncio.Lock` — **claims the next
  `queued` job ordered by `(queue_position, created_at)`** and marks it
  `downloading` atomically, so two workers can never claim the same job.
- Reordering is a plain DB update of `queue_position`. Positions are persistent
  and survive restarts; the UI reads position directly.
- Stale/extra tokens (e.g. a queued job cancelled before pickup) simply cause a
  harmless no-op wake: the worker claims nothing and loops back to waiting.

Rejected alternatives:

- **Rebuild the `asyncio.Queue` on each reorder** — drain to a list, reorder,
  re-put. Racy (a worker may have already pulled an item), non-persistent,
  ordering lost on restart.
- **`asyncio.PriorityQueue` keyed by position** — items already enqueued can't be
  mutated, so reorder still needs a racy drain/rebuild.

## Backend design

### Model + migration (`models.py`, `db.py`)

- `Job.queue_position: int = Field(default=0, index=True)`.
- Additive migration entry: `("job", "queue_position", "INTEGER NOT NULL DEFAULT 0")`.
- On **enqueue** (single create, batch create, scheduled-job-becomes-due),
  assign `queue_position = (max queue_position among queued jobs) + 1` so new
  work appends to the end. Batch import assigns sequential positions.

### Queue worker (`queue.py`)

- Add an `asyncio.Lock` (`_claim_lock`).
- The `asyncio.Queue` still receives one token per enqueue and one per
  recovered job on startup; `enqueue()` continues to push a token.
- Worker loop: `await self._queue.get()` (block for a token) → under
  `_claim_lock`, run a claim query:
  `select queued jobs order by queue_position, created_at limit 1`; if found,
  set it to `downloading`, publish the state snapshot, and return its id; if none,
  loop back to waiting. Then process the claimed job.
- Startup recovery: interrupted `queued/downloading/post-processing` jobs are
  reset to `queued` (retaining their `queue_position`, or assigning one if 0) and
  one token is pushed per job — unchanged in spirit from today.
- `cancel()` semantics are unchanged (queued → mark cancelled; running → set the
  cancel event).

### Endpoints (`routers/downloads.py`, `schemas.py`)

- `POST /api/downloads/reorder` — body `{ ordered_ids: number[] }`. Validates the
  ids are currently `queued`; reassigns `queue_position` in the given order
  (0..n-1 or 1..n). Ids not in `queued` are ignored/rejected (422 if any id is
  unknown or not queued — decide in plan; default: ignore non-queued, 404 on
  unknown). Returns the updated queued list (or 204). Drag-and-drop sends the
  full new order; up/down/"Download next" buttons compute the new order
  client-side and hit the same endpoint.
- `POST /api/downloads/cancel` — body `{ ids: number[] }`. Cancels each via
  `manager.cancel`; returns `{ cancelled: number }`. Powers multi-select cancel
  and "Cancel all queued" (frontend passes all queued ids). Terminal/unknown ids
  are skipped, not fatal.
- Expose `queue_position` in `JobRead`.

## Frontend design

### Navigation + placement

- Add a **Queue** entry to `Header` `NAV` (after "Download"), icon
  `ListOrdered` (or similar lucide icon), view key `"queue"`.
- Remove the `ActiveDownloads` section from the home view in `App.tsx`; home
  becomes `SubmitView` + `BatchImport`. `ActiveDownloads.tsx` is superseded by
  the Queue page (delete or repurpose).

### `QueuePage.tsx`

- One `useQuery(["downloads"])` (same key/refetch pattern as today), filtered to
  active statuses, grouped into three sections:
  - **Downloading now** — `downloading` + `post-processing`.
  - **Up next** — `queued`, ordered by `queue_position`.
  - **Scheduled** — `scheduled` (shows scheduled time, not reorderable).
- Section header: total active count + **Cancel all queued** button + a
  **selection mode** toggle (checkboxes on queued cards → a toolbar
  "Cancel N selected").
- Empty state mirrors today's "No active downloads…" affordance.

### Reordering (queued items only)

- Native HTML5 drag-and-drop (`draggable`, `onDragStart/Over/Drop`) — **no new
  dependency** — for pointer reordering.
- Move-up / move-down / **Download next** (move-to-top) buttons for
  keyboard/touch/accessibility.
- A position badge (`#1`, `#2`, …) on each queued card.
- Both interactions produce a new ordered id list and call
  `api.reorderDownloads(orderedIds)`; the mutation invalidates `["downloads"]`.
  Optimistic reorder is optional (nice-to-have) — decide in plan.
- Downloading, post-processing, and scheduled items are **not** reorderable.

### Component composition

- `DownloadCard` stays the pure progress/cancel card.
- A thin `QueueItem` wrapper adds, for `queued` jobs: drag handle, position badge,
  up/down + "Download next" buttons, and a selection checkbox — composing
  `DownloadCard` for the body.

### API client + types (`lib/api.ts`, `lib/types.ts`)

- `Job.queue_position: number` added to the `Job` type.
- `api.reorderDownloads(orderedIds: number[])` → `POST /api/downloads/reorder`.
- `api.cancelDownloads(ids: number[])` → `POST /api/downloads/cancel`.

## Error handling

- Reorder/cancel mutations surface failures via `toast.error` (existing sonner
  pattern in `DownloadCard`).
- Cancelling an already-terminal job is a no-op server-side (skipped in bulk;
  409 preserved for the single-id endpoint).
- A reorder that references a job that just started downloading (no longer
  queued) is ignored for that id; the query refetch reconciles UI state.

## Testing

- **Backend (`backend/tests/test_api.py`)**:
  - `queue_position` assigned on create/batch (appends to end).
  - `POST /api/downloads/reorder` reassigns positions; workers claim in the new
    order (enqueue 3, reorder, assert processing/claim order).
  - `POST /api/downloads/cancel` bulk-cancels, returns count, skips terminal ids.
- **Frontend**: no test harness exists (backend-only test suite). The Queue page,
  drag-and-drop, and bulk actions are verified manually via the run/verify skill.

## Out of scope (YAGNI)

- Pause/resume of an in-flight download (yt-dlp resume is a separate concern).
- Per-job priority weights beyond explicit ordering.
- Reordering across restarts is handled by persistence, but no cross-session
  "saved orderings" feature.
- Home-page compact queue summary (we chose to move the queue entirely to its tab).

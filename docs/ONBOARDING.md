# Developer Onboarding

Orientation for a developer who just cloned **yt-dlp Dashboard** and needs to understand
what it is, how to run it, and how the pieces fit — so you know where to make a change.

For install-per-OS and deployment details, see [SETUP.md](SETUP.md). For the user-facing
feature tour, see the [README](../README.md). This doc is about the *codebase*.

## What it is

A self-hosted, single-user web dashboard around [yt-dlp](https://github.com/yt-dlp/yt-dlp).
You paste a URL, the app probes it for metadata and available formats, you pick a
quality/format and options, and it downloads the file to a directory on the host — streaming
live progress to the browser over a WebSocket. Finished downloads are kept in a searchable
history backed by SQLite.

There is **no authentication** and it assumes a single trusted user on a LAN/VPN.

## The stack in one glance

| Layer | Tech | Where |
| --- | --- | --- |
| Frontend | React 19 + Vite 6, TypeScript, Tailwind, Radix UI, TanStack Query, `sonner` toasts | [frontend/src/](../frontend/src/) |
| Backend | FastAPI + uvicorn (Python 3.11+), managed by `uv` | [backend/app/](../backend/app/) |
| Downloader | yt-dlp used **as a library** (no shelling out), ffmpeg for post-processing | [backend/app/downloader.py](../backend/app/downloader.py) |
| Persistence | SQLite via SQLModel | [backend/app/models.py](../backend/app/models.py) |
| Realtime | In-process pub/sub broker → WebSocket per job | [backend/app/broker.py](../backend/app/broker.py), [backend/app/routers/ws.py](../backend/app/routers/ws.py) |

In **dev** the frontend (Vite, port 5173) and backend (uvicorn, port 8000) run as two
processes; Vite proxies `/api` and `/ws` to the backend. In **production** the frontend is
built to static files and served by FastAPI itself on a single port (see
`YTDLP_STATIC_DIR` in [main.py](../backend/app/main.py#L75)).

## Run it locally

```bash
# Terminal 1 — backend on :8000
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend on :5173
cd frontend
pnpm install
pnpm dev
```

Open **http://localhost:5173**. You need `ffmpeg` on your `PATH` for merging formats, audio
extraction, thumbnails, and SponsorBlock — the backend logs a warning at startup if it's
missing (see [main.py](../backend/app/main.py#L28-L35)). Full prerequisites are in
[SETUP.md](SETUP.md#environment-setup-per-os).

Useful checks:

- API docs (auto-generated): http://localhost:8000/docs
- Health + ffmpeg status: http://localhost:8000/api/health
- Frontend type-check / lint: `cd frontend && pnpm lint`

## How a download flows through the system

This is the single most important thing to understand. Follow one download end to end:

1. **Probe** — The user submits a URL. The frontend calls `POST /api/probe`
   ([probe.py](../backend/app/routers/probe.py)), which runs `probe()` in
   [downloader.py](../backend/app/downloader.py#L538) off the event loop via
   `asyncio.to_thread`. yt-dlp extracts metadata + a normalized list of formats **without
   downloading**. The UI renders the metadata card and format picker.

2. **Create job** — The user picks options and the frontend calls `POST /api/downloads`
   ([downloads.py](../backend/app/routers/downloads.py#L148)). A `Job` row is inserted
   (status `queued`), best-effort metadata is fetched so history has a title immediately,
   and the id is handed to the job manager via `manager.enqueue(job.id)`.

3. **Queue + worker pool** — [queue.py](../backend/app/queue.py) holds an `asyncio.Queue`
   of job ids and a pool of worker tasks (size = `max_concurrency` setting). A worker pulls
   an id, loads an options snapshot, sets status `downloading`, and runs the **blocking**
   `run_download()` in a thread executor (`asyncio.to_thread`) so the event loop stays free.

4. **Progress** — Inside the download thread, yt-dlp calls progress/postprocessor hooks.
   These are normalized ([`_normalize_progress`](../backend/app/downloader.py#L776)) and
   forwarded through the worker's `on_event` callback, which (a) throttles DB writes to
   ~2/sec, always writing on status change, and (b) publishes a snapshot to the
   **broker** using `publish_threadsafe` (safe to call from the worker thread — it bounces
   onto the captured event loop).

5. **Stream to browser** — The browser opens `ws://…/ws/downloads/{id}`
   ([ws.py](../backend/app/routers/ws.py)). The endpoint sends the current persisted state
   immediately, then subscribes to the broker and relays each update. The
   [`useJobSocket`](../frontend/src/hooks/useJobSocket.ts) hook drives the live progress bar
   and auto-reconnects until the job reaches a terminal state.

6. **Finalize** — On success/failure/cancel the worker calls `_finalize()`, writing the
   terminal status, filepath, filesize, and metadata, and publishing a final snapshot. The
   WebSocket sees a terminal `state` message and closes.

7. **Get the file** — The completed file is downloadable via `GET /api/files/{id}`
   ([files.py](../backend/app/routers/files.py)), which streams it as an octet-stream.

Two details worth internalizing:

- **Cancellation** is cooperative: `manager.cancel()` sets a `threading.Event`; the download
  thread polls `is_cancelled()` inside the progress hook and raises `DownloadCancelled`.
  Queued-but-not-yet-running jobs are marked cancelled directly.
- **Crash recovery**: on startup, `manager.start()` re-queues any jobs left in a
  non-terminal state ([queue.py](../backend/app/queue.py#L244-L259)) so an interrupted
  download resumes after a restart.

## Backend map

| File | Responsibility |
| --- | --- |
| [main.py](../backend/app/main.py) | FastAPI app, lifespan (DB init, ffmpeg probe, start/stop job manager), CORS, router wiring, optional static SPA mount |
| [config.py](../backend/app/config.py) | Bootstrap config from `YTDLP_*` env vars (DB URL, download dir, static dir, CORS). Runtime-mutable settings live in the DB instead |
| [models.py](../backend/app/models.py) | SQLModel tables: `Job` (one download + its lifecycle, incl. the `options` JSON blob and `scheduled_at`) and the singleton `AppSettings` row; `JobStatus` enum + `TERMINAL_STATES` |
| [options.py](../backend/app/options.py) | **`DownloadOptions`** — the canonical set of every yt-dlp knob the UI exposes; `merge_legacy()` and `redact()` (secret masking). Persisted as `Job.options` JSON |
| [schemas.py](../backend/app/schemas.py) | Pydantic request/response models — the **source of truth** for the hand-written TS client |
| [db.py](../backend/app/db.py) | Engine, session helpers, table creation + settings seed, and `_run_migrations()` (additive `ALTER TABLE ADD COLUMN` list — no migration framework) |
| [downloader.py](../backend/app/downloader.py) | yt-dlp wrappers: `probe()`, `probe_raw()`, `search()`, `expand_entries()` (flatten a channel/playlist into individual videos), `build_ydl_opts()` (translates `DownloadOptions`), `build_match_filters()`, `parse_bytes()`/`parse_download_sections()`, `run_download()` |
| [queue.py](../backend/app/queue.py) | `JobManager`: async queue, worker pool, concurrency scaling, cancel, DB throttling, finalize |
| [automation.py](../backend/app/automation.py) | `Watcher` background loop: promotes due `scheduled` jobs and auto-queues URLs from a watch folder's `*.txt` files |
| [broker.py](../backend/app/broker.py) | In-process per-job pub/sub with last-message caching and thread-safe publish |
| [routers/](../backend/app/routers/) | `probe` (+`/raw`), `search`, `artist` (`/expand`), `downloads` (+`/batch`), `settings`, `files`, `ws` HTTP/WS endpoints |

### API surface

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/probe` | Metadata + formats, no download |
| POST | `/api/probe/raw` | Full sanitized yt-dlp info JSON (raw extraction) |
| POST | `/api/search` | ytsearch / ytsearchdate / scsearch results |
| POST | `/api/artist/expand` | Flatten a channel/playlist URL into its individual videos (`extract_flat`, no download) |
| POST | `/api/downloads` | Create a job (returns `{id}`); optional `scheduled_at` + `options` |
| POST | `/api/downloads/batch` | Queue many URLs at once (returns `{ids, count}`) |
| GET | `/api/downloads` | Paginated history, optional `status` filter |
| GET | `/api/downloads/{id}` | Single job |
| POST | `/api/downloads/{id}/cancel` | Cancel an active/queued job |
| DELETE | `/api/downloads/{id}` | Delete job row (optionally the file) |
| GET | `/api/settings` · PUT | Read / update runtime settings |
| GET | `/api/files/{id}` | Download the finished file |
| WS | `/ws/downloads/{id}` | Live progress stream |
| GET | `/api/health` | Status + ffmpeg availability |

## Frontend map

Single-page app with views switched by local state in
[App.tsx](../frontend/src/App.tsx): **home** (submit + batch import + active downloads),
**queue**, **search**, **artist**, **lyrics**, **history**, and **settings** (see
[Header.tsx](../frontend/src/components/Header.tsx) for the `View` union + nav).

| Area | What's there |
| --- | --- |
| [lib/api.ts](../frontend/src/lib/api.ts) | Typed fetch client + `ApiError`; `wsUrl()` builder |
| [lib/types.ts](../frontend/src/lib/types.ts) | TS mirror of the backend schemas incl. `DownloadOptions` (keep in sync with [schemas.py](../backend/app/schemas.py) / [options.py](../backend/app/options.py)) |
| [hooks/useJobSocket.ts](../frontend/src/hooks/useJobSocket.ts) | WebSocket subscription with auto-reconnect and terminal-state callback |
| [components/OptionsPanel.tsx](../frontend/src/components/OptionsPanel.tsx) | The collapsible advanced-options editor — **one section per feature phase** (subtitles, thumbnails, metadata, audio, playlist, download control, network, cookies, auth, filtering, post-processing, developer, file organization). Add new knobs here |
| [components/ArtistPage.tsx](../frontend/src/components/ArtistPage.tsx) | Expand a channel/playlist URL (`/api/artist/expand`), select which videos to grab, then queue them via the existing `/api/downloads/batch` endpoint — one job per song |
| `components/` | `SubmitView`, `SearchPage`, `ArtistPage`, `BatchImport`, `MetadataCard`, `FormatPicker`, `OptionsPanel`, `QueuePage`, `DownloadCard`, `SpeedGraph`, `HistoryTable`, `LyricsPage`, `SettingsPage`, `Header`, `StatusBadge`, plus a `components/ui/` set of Radix-based primitives |

Server state is managed with **TanStack Query**; the API client throws `ApiError` carrying
the backend's `detail` message so UI toasts can show human-readable errors.

## Conventions & gotchas

- **The API contract is defined once in Python** ([schemas.py](../backend/app/schemas.py))
  and hand-mirrored in [lib/types.ts](../frontend/src/lib/types.ts). Change one, change the
  other — there is no codegen.
- **Static vs. runtime config split**: env-var bootstrap config is in
  [config.py](../backend/app/config.py); anything a user can change at runtime (download dir,
  default format, concurrency, naming template) lives in the `AppSettings` DB row.
- **Blocking work never runs on the event loop** — probes and downloads always go through
  `asyncio.to_thread`. Anything touching the DB from a worker uses `session_scope()` with
  `check_same_thread=False`.
- **Concurrency is live-adjustable**: changing `max_concurrency` in settings calls
  `manager.set_concurrency()`, which scales the worker pool without a restart.
- **Options flow through one model**: every yt-dlp knob lives on `DownloadOptions`
  ([options.py](../backend/app/options.py)), is stored as the `Job.options` JSON blob, and is
  translated in `build_ydl_opts()`. Adding a feature almost never needs a DB migration.
- **Schema changes use the additive migration list** in [db.py](../backend/app/db.py)
  (`_MIGRATIONS`): append `(table, column, DDL-with-DEFAULT)` — it runs `ALTER TABLE ADD COLUMN`
  only when the column is missing. New `DownloadOptions` fields don't need an entry.
- **Secrets are masked**: option values in `SENSITIVE_KEYS` are redacted by `options.redact()`
  before any job is returned from the API.
- Python is formatted with `ruff` (line length 100); dependencies via `uv` and
  `pyproject.toml`. Frontend uses `pnpm`.

## Where to make common changes

| I want to… | Start here |
| --- | --- |
| Add a download option (e.g. a new checkbox) | Add a field to `DownloadOptions` ([options.py](../backend/app/options.py)) → translate it in `build_ydl_opts()` → mirror it in the frontend `DownloadOptions` type ([types.ts](../frontend/src/lib/types.ts)) → add a control to the matching section of [OptionsPanel.tsx](../frontend/src/components/OptionsPanel.tsx). No DB migration needed — options are stored in the `Job.options` JSON column. |
| Add a new quality preset | `QUALITY_PRESETS` in [downloader.py](../backend/app/downloader.py#L604) |
| Change progress/throttle behavior | `_make_on_event` and `_DB_THROTTLE_S` in [queue.py](../backend/app/queue.py) |
| Add an API endpoint | new file in [routers/](../backend/app/routers/), register it in [main.py](../backend/app/main.py) |
| Add a runtime setting | `AppSettings` model, `SettingsRead`/`SettingsUpdate` schemas, `settings.py` router, `SettingsPage` |
| Change the output filename format | `default_output_template` / `naming` in settings; consumed in `build_ydl_opts()` |

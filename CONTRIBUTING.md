# Contributing to yt-dlp Dashboard

Thanks for your interest in improving the project! Contributions of all kinds are welcome — bug reports, features, docs, and fixes.

## Development setup

You need Python 3.11+ (via [uv](https://docs.astral.sh/uv/)), Node 20+ with [pnpm](https://pnpm.io), and ffmpeg on your `PATH`. See [docs/SETUP.md](docs/SETUP.md) for per-OS instructions.

```bash
# Backend (http://localhost:8000, docs at /docs)
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

# Frontend (http://localhost:5173) — in a second terminal
cd frontend
pnpm install
pnpm dev
```

## Project layout

```
backend/app/
  main.py        FastAPI app, lifespan (ffmpeg check, DB init, queue start), static serving
  config.py      env-overridable bootstrap config
  db.py          engine/session/init + settings accessor
  models.py      SQLModel tables (Job, AppSettings) + JobStatus
  schemas.py     Pydantic request/response models  ← API contract (source of truth)
  downloader.py  yt-dlp wrappers: probe() + run_download() + ffmpeg detection
  queue.py       async job queue + worker pool + cancellation + restart recovery
  broker.py      per-job progress pub/sub bridge (thread → asyncio)
  routers/       probe, downloads, settings, files, ws

frontend/src/
  lib/api.ts     typed fetch client + WebSocket URL helper
  lib/types.ts   TypeScript mirror of schemas.py  ← keep in sync
  hooks/         useJobSocket (live progress)
  components/    SubmitView, FormatPicker, ActiveDownloads, HistoryTable, SettingsPage, ui/
```

## Guidelines

- **Keep the API contract in sync.** `backend/app/schemas.py` is the source of truth; mirror any field changes in `frontend/src/lib/types.ts` (and the client in `lib/api.ts`).
- **Don't shell out to the yt-dlp CLI.** Use the library API (`from yt_dlp import YoutubeDL`). Run blocking calls in a thread executor.
- **Surface errors as readable messages**, not 500s — follow the pattern in `routers/probe.py` and `downloader.py`.
- **Match the surrounding style.** The frontend uses Tailwind + shadcn-style components; reuse the `ui/` primitives.

## Checks before opening a PR

```bash
# Frontend: type-check and production build
cd frontend && pnpm build

# Backend: import + endpoints sanity (or run the app and hit /docs)
cd backend && uv run python -c "import app.main"
```

Please describe the change and how you tested it in your pull request. For larger features, opening an issue first to discuss the approach is appreciated.

## Reporting bugs

Include: the URL or scenario (redact anything private), what you expected, what happened, backend logs, and your yt-dlp version (`cd backend && uv run python -c "import yt_dlp; print(yt_dlp.version.__version__)"`). Many extraction bugs are fixed simply by updating yt-dlp — see [Updating yt-dlp](docs/SETUP.md#updating-the-app-and-yt-dlp).

# Setup &amp; Operations Guide

A detailed install and operations guide for **yt-dlp Dashboard**. For a quick overview see the [README](../README.md).

## Contents

- [Architecture](#architecture)
- [Environment setup per OS](#environment-setup-per-os)
- [Running in development](#running-in-development)
- [Running in production](#running-in-production)
- [Docker &amp; docker-compose](#docker--docker-compose)
- [Reverse proxy (nginx)](#reverse-proxy-nginx)
- [Running as a systemd service](#running-as-a-systemd-service)
- [Updating the app and yt-dlp](#updating-the-app-and-yt-dlp)
- [Backup &amp; reset of the database](#backup--reset-of-the-database)

## Architecture

```
┌──────────────┐     /api, /ws      ┌─────────────────────────────┐
│  React SPA   │ ─────────────────▶ │  FastAPI (uvicorn)           │
│ (Vite build) │ ◀───────────────── │  ├─ /api/probe  (yt-dlp)     │
└──────────────┘   JSON + WebSocket │  ├─ /api/downloads + queue   │
                                    │  ├─ /ws/downloads/{id}       │
                                    │  └─ /api/settings, /api/files│
                                    │  async queue → worker pool   │
                                    │  yt-dlp in thread executor   │
                                    │  progress → broker → WS      │
                                    └──────────────┬──────────────┘
                                                   │
                                       ┌───────────┴───────────┐
                                       │ SQLite (jobs+settings) │
                                       │ download directory     │
                                       │ ffmpeg (post-process)  │
                                       └────────────────────────┘
```

- **Backend** (`backend/app/`): FastAPI app embedding yt-dlp as a library. Downloads run in a thread executor so the event loop stays responsive; an `asyncio.Queue` + worker pool enforces max concurrency. A pub/sub broker forwards yt-dlp progress-hook dicts to WebSocket subscribers per job id.
- **Frontend** (`frontend/src/`): React + Vite SPA. In dev, Vite proxies `/api` and `/ws` to the backend. In production, the built bundle is served by FastAPI itself.
- **Persistence**: a single SQLite database holds the job history and the settings row; downloads land in the configured download directory.

## Environment setup per OS

You need **Python 3.11+** (managed by uv), **Node 20+**, **pnpm**, and **ffmpeg**.

### macOS

```bash
# Homebrew
brew install ffmpeg node
curl -LsSf https://astral.sh/uv/install.sh | sh
corepack enable && corepack prepare pnpm@latest --activate
```

### Debian / Ubuntu

```bash
sudo apt update
sudo apt install -y ffmpeg curl
# Node 20 LTS via NodeSource (or use your distro's nodejs if ≥ 20)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
curl -LsSf https://astral.sh/uv/install.sh | sh
corepack enable && corepack prepare pnpm@latest --activate
```

### Windows

```powershell
winget install Gyan.FFmpeg
winget install OpenJS.NodeJS.LTS
winget install astral-sh.uv
corepack enable
corepack prepare pnpm@latest --activate
```

Verify everything is on your `PATH`:

```bash
ffmpeg -version
python --version   # or: uv python list
node --version
pnpm --version
uv --version
```

## Running in development

Two processes with hot reload.

```bash
# Terminal 1 — backend (http://localhost:8000)
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend (http://localhost:5173)
cd frontend
pnpm install
pnpm dev
```

Open **http://localhost:5173**. Vite proxies API and WebSocket traffic to port 8000.

To point the dev proxy at a different backend host/port:

```bash
VITE_BACKEND=http://192.168.1.10:8000 pnpm dev
```

## Running in production

You have two good options.

### Option A — single process (FastAPI serves the SPA)

Build the frontend once, then run uvicorn with `YTDLP_STATIC_DIR` pointing at the build. This is exactly what the Docker image does.

```bash
# 1) Build the frontend
cd frontend && pnpm install && pnpm build      # outputs frontend/dist

# 2) Run the backend serving the bundle
cd ../backend
uv sync --no-dev
YTDLP_STATIC_DIR=../frontend/dist \
YTDLP_DOWNLOAD_DIR=/srv/downloads \
YTDLP_DATABASE_URL=sqlite:////srv/ytdlp/app.db \
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The app (UI + API) is then available on a single port, `8000`.

### Option B — Docker (recommended)

See below — it bundles ffmpeg and does the build for you.

## Docker &amp; docker-compose

The repository ships a multi-stage `Dockerfile` (builds the frontend, then runs FastAPI with ffmpeg installed) and a `docker-compose.yml`.

```bash
docker compose up --build -d      # start in the background
docker compose logs -f            # follow logs
docker compose down               # stop
```

App: **http://localhost:8000**.

### Volume mapping

`docker-compose.yml` maps two host directories:

| Host path | Container path | Purpose |
| --- | --- | --- |
| `./downloads` | `/downloads` | Finished files (`YTDLP_DOWNLOAD_DIR`) |
| `./data` | `/data` | SQLite database `app.db` (`YTDLP_DATABASE_URL`) |

To store downloads somewhere else on the host (e.g. a NAS mount), edit the volume:

```yaml
    volumes:
      - /mnt/media/youtube:/downloads
      - ./data:/data
```

To change the published port, edit the `ports` mapping, e.g. `"8080:8000"`.

## Reverse proxy (nginx)

To serve the dashboard behind nginx (TLS, a subdomain, etc.), proxy both HTTP and WebSocket traffic to the app on port 8000:

```nginx
server {
    listen 80;
    server_name ytdlp.example.com;

    client_max_body_size 0;          # don't cap file downloads

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket upgrade for /ws/downloads/{id}
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;     # long-lived progress sockets
    }
}
```

Put a TLS terminator (Certbot, Caddy, or your platform's) in front as usual. Because the app is **single-user with no authentication**, do not expose it directly to the public internet — keep it on a LAN/VPN or add auth at the proxy (e.g. HTTP basic auth or an SSO forward-auth).

## Running as a systemd service

For a manual (non-Docker) production install, run the single-process variant under systemd.

`/etc/systemd/system/ytdlp-dashboard.service`:

```ini
[Unit]
Description=yt-dlp Dashboard
After=network.target

[Service]
Type=simple
User=ytdlp
WorkingDirectory=/opt/yt-dlp-dashboard/backend
Environment=YTDLP_STATIC_DIR=/opt/yt-dlp-dashboard/frontend/dist
Environment=YTDLP_DOWNLOAD_DIR=/srv/downloads
Environment=YTDLP_DATABASE_URL=sqlite:////srv/ytdlp/app.db
ExecStart=/usr/local/bin/uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ytdlp-dashboard
sudo systemctl status ytdlp-dashboard
journalctl -u ytdlp-dashboard -f
```

(Adjust the `uv` path to the output of `which uv` for your service user.)

## Updating the app and yt-dlp

**Update the app code:**

```bash
git pull
# Docker:
docker compose build --no-cache && docker compose up -d
# Manual:
cd backend && uv sync
cd ../frontend && pnpm install && pnpm build
```

**Update only yt-dlp** (sites change often; do this when extraction breaks):

```bash
# Manual install
cd backend
uv lock --upgrade-package yt-dlp
uv sync

# Docker — rebuild so the new version is baked in
docker compose build --no-cache
docker compose up -d
```

## Backup &amp; reset of the database

The entire history + settings live in one SQLite file (`app.db`).

**Back up** (safe while running, since SQLite supports online backup):

```bash
# Docker (db at ./data/app.db on the host)
cp ./data/app.db ./data/app.db.bak

# Manual (default dev location)
cp backend/data/app.db backend/data/app.db.bak
```

For a guaranteed-consistent copy, stop the app first, or use the SQLite CLI:

```bash
sqlite3 ./data/app.db ".backup './data/app-backup.db'"
```

**Reset** to a clean slate (clears all history and settings; does **not** delete downloaded files):

```bash
# Docker
docker compose down
rm ./data/app.db
docker compose up -d        # a fresh DB is created and seeded on startup

# Manual
rm backend/data/app.db      # recreated on next backend start
```

Downloaded files are independent of the database — deleting `app.db` only clears the dashboard's history, not the files on disk.

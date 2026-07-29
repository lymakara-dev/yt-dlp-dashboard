"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .automation import watcher
from .config import config
from .db import init_db
from .downloader import ffmpeg_info
from .queue import manager
from .routers import artist, downloads, files, lyrics, probe, search, settings, ws
from .schemas import HealthResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ytdlp-dashboard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    has_ffmpeg, version = ffmpeg_info()
    if has_ffmpeg:
        log.info("ffmpeg detected: %s", version)
    else:
        log.warning(
            "ffmpeg NOT found on PATH. Merging formats, audio extraction, "
            "thumbnail embedding and SponsorBlock will fail. Install ffmpeg."
        )
    app.state.ffmpeg = has_ffmpeg
    app.state.ffmpeg_version = version

    await manager.start()
    await watcher.start()

    yield

    await watcher.stop()
    await manager.shutdown()


app = FastAPI(title="yt-dlp Dashboard", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(probe.router)
app.include_router(search.router)
app.include_router(artist.router)
app.include_router(lyrics.router)
app.include_router(downloads.router)
app.include_router(settings.router)
app.include_router(files.router)
app.include_router(ws.router)


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        ffmpeg=app.state.ffmpeg,
        ffmpeg_version=app.state.ffmpeg_version,
    )


# Serve the built frontend (production/Docker) if present. Registered last so the
# API and WebSocket routes above always take precedence. html=True serves
# index.html for the SPA root.
if config.static_dir and os.path.isdir(config.static_dir):
    app.mount("/", StaticFiles(directory=config.static_dir, html=True), name="static")

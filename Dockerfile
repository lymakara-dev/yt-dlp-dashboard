# syntax=docker/dockerfile:1

# ---------- Stage 1: build the frontend ----------
FROM node:22-slim AS frontend
WORKDIR /frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml* frontend/.npmrc ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# ---------- Stage 2: backend + ffmpeg, serving the built SPA ----------
FROM python:3.11-slim AS runtime

# ffmpeg is required for merging formats, audio extraction, thumbnails, SponsorBlock.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# uv for dependency management.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    YTDLP_STATIC_DIR=/app/static \
    YTDLP_DOWNLOAD_DIR=/downloads \
    YTDLP_DATABASE_URL=sqlite:////data/app.db

# Install Python dependencies (cached unless lockfile changes).
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Application code + built frontend.
COPY backend/app ./app
COPY --from=frontend /frontend/dist ./static

# Persisted data + downloads (mount volumes here in production).
RUN mkdir -p /data /downloads

EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

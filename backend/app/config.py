"""Static application configuration (env-overridable).

Runtime-mutable settings (download dir, default format, concurrency, naming)
live in the database via the AppSettings model — see models.py / routers/settings.py.
This module only holds bootstrap config that must be known before the DB is open.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root: backend/
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="YTDLP_", env_file=".env", extra="ignore")

    # Where the SQLite database file lives.
    database_url: str = f"sqlite:///{DATA_DIR / 'app.db'}"

    # Default download directory (also the seed value for AppSettings on first run).
    download_dir: str = str(DATA_DIR / "downloads")

    # Optional directory of pre-built frontend assets to serve (production/Docker).
    # When set and present, FastAPI serves the SPA at "/". Empty in dev (Vite serves it).
    static_dir: str = ""

    # CORS origins for the Vite dev server.
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Telegram bot token (from @BotFather). Bootstrap-only, like static_dir: never
    # stored in the DB or returned by any API response. Empty disables the bot.
    telegram_bot_token: str = ""


config = Config()

# Ensure base data directories exist at import time.
DATA_DIR.mkdir(parents=True, exist_ok=True)
Path(config.download_dir).mkdir(parents=True, exist_ok=True)

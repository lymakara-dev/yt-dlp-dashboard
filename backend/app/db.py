"""Database engine + session helpers and one-time initialization."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine, select

from .config import config
from .models import AppSettings

# Lightweight additive migrations: (table, column, column DDL) applied only when
# the column is missing. SQLite supports ADD COLUMN; every entry must carry a
# DEFAULT so it can be added to a table that already has rows. This replaces a
# full migration framework for our append-only schema evolution.
_MIGRATIONS: list[tuple[str, str, str]] = [
    ("job", "options", "JSON NOT NULL DEFAULT '{}'"),
    ("appsettings", "watch_folder", "TEXT NOT NULL DEFAULT ''"),
    ("appsettings", "watch_interval", "INTEGER NOT NULL DEFAULT 30"),
]


def _run_migrations() -> None:
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, column, ddl in _MIGRATIONS:
            if table not in tables:
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            if column not in existing:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}'))

# check_same_thread=False because worker threads (thread executor) touch the DB.
engine = create_engine(
    config.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """Create tables, apply additive migrations, and seed settings."""
    SQLModel.metadata.create_all(engine)
    _run_migrations()
    with Session(engine) as session:
        existing = session.get(AppSettings, 1)
        if existing is None:
            session.add(
                AppSettings(id=1, download_dir=config.download_dir)
            )
            session.commit()


def get_settings(session: Session) -> AppSettings:
    settings = session.get(AppSettings, 1)
    if settings is None:  # defensive; init_db should have seeded it
        settings = AppSettings(id=1, download_dir=config.download_dir)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


@contextmanager
def session_scope() -> Iterator[Session]:
    """Standalone session for use outside of request dependencies (workers)."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with Session(engine) as session:
        yield session


__all__ = ["engine", "init_db", "get_session", "session_scope", "get_settings", "select"]

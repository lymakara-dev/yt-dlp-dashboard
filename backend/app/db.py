"""Database engine + session helpers and one-time initialization."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine, select

from .config import config
from .models import AppSettings

# check_same_thread=False because worker threads (thread executor) touch the DB.
engine = create_engine(
    config.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """Create tables and seed the singleton settings row."""
    SQLModel.metadata.create_all(engine)
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

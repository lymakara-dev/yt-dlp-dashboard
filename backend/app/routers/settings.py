"""GET/PUT /api/settings — user-configurable runtime settings."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session, get_settings
from ..queue import manager
from ..schemas import SettingsRead, SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsRead)
def read_settings(session: Session = Depends(get_session)) -> SettingsRead:
    return SettingsRead.model_validate(get_settings(session))


@router.put("", response_model=SettingsRead)
def update_settings(
    update: SettingsUpdate, session: Session = Depends(get_session)
) -> SettingsRead:
    settings = get_settings(session)

    if update.download_dir is not None:
        path = Path(update.download_dir).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(
                status_code=400, detail=f"Cannot create download directory: {exc}"
            ) from exc
        settings.download_dir = str(path)

    if update.max_concurrency is not None:
        if update.max_concurrency < 1 or update.max_concurrency > 16:
            raise HTTPException(status_code=400, detail="max_concurrency must be 1–16.")
        settings.max_concurrency = update.max_concurrency

    if update.default_format is not None:
        settings.default_format = update.default_format
    if update.default_output_template is not None:
        settings.default_output_template = update.default_output_template
    if update.naming is not None:
        settings.naming = update.naming

    session.add(settings)
    session.commit()
    session.refresh(settings)

    # Apply concurrency change to the live worker pool.
    if update.max_concurrency is not None:
        manager.set_concurrency(settings.max_concurrency)

    return SettingsRead.model_validate(settings)

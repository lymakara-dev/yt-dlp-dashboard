"""GET /api/telegram/status — read-only bot connection state for the Settings page."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..config import config
from ..db import get_session, get_settings
from ..schemas import TelegramStatusResponse
from ..telegram_bot import telegram_bot

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.get("/status", response_model=TelegramStatusResponse)
def telegram_status(session: Session = Depends(get_session)) -> TelegramStatusResponse:
    settings = get_settings(session)
    return TelegramStatusResponse(
        configured=bool(config.telegram_bot_token),
        enabled=settings.telegram_enabled,
        connected=telegram_bot.is_polling,
        bot_username=telegram_bot.bot_username,
    )

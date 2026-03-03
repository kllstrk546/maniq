from __future__ import annotations

import logging
import sqlite3

import aiosqlite
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent

from app.loader import dp

logger = logging.getLogger(__name__)


async def _notify_user(update, text: str) -> None:
    try:
        if update.callback_query:
            cq = update.callback_query
            if cq.message:
                await cq.message.answer(text)
            await cq.answer()
            return

        if update.message:
            await update.message.answer(text)
            return
    except Exception:
        logger.exception("Failed to notify user about handled error")


@dp.error()
async def on_error(event: ErrorEvent) -> bool:
    exc = event.exception

    if isinstance(exc, TelegramAPIError):
        logger.warning("Handled TelegramAPIError: %s", exc)
        await _notify_user(
            event.update,
            "Помилка Telegram API. Спробуйте ще раз через кілька секунд.",
        )
        return True

    if isinstance(exc, (aiosqlite.IntegrityError, sqlite3.IntegrityError)):
        logger.warning("Handled IntegrityError: %s", exc)
        await _notify_user(
            event.update,
            "Не вдалося виконати дію через конфлікт даних. Оновіть екран і спробуйте ще раз.",
        )
        return True

    logger.exception("Unhandled error", exc_info=exc)
    await _notify_user(
        event.update,
        "Сталася неочікувана помилка. Спробуйте ще раз.",
    )
    return True

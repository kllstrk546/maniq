from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot
from aiogram.types import User

from app.database import repo_bookings
from config import ADMIN_ID


async def cancel_booking_for_user(booking_id: int, user_id: int) -> Optional[dict]:
    """Скасовує активний запис користувача та повертає дані скасування."""
    return await repo_bookings.cancel_booking_by_user(booking_id=booking_id, user_id=user_id)


async def notify_admin_about_cancellation(
    bot: Bot,
    booking: dict,
    telegram_user: User,
) -> None:
    """Сповіщення адміна про скасування запису користувачем."""
    username = f"@{telegram_user.username}" if telegram_user.username else "без username"
    text = (
        "❌ Користувач скасував запис\n\n"
        f"User ID: <code>{telegram_user.id}</code>\n"
        f"Username: {username}\n"
        f"Ім'я в записі: {booking.get('client_name') or '-'}\n"
        f"Телефон: {booking.get('client_phone') or '-'}\n"
        f"Дата: {booking['work_date']}\n"
        f"Час: {booking['slot_time'][:5]}"
    )

    try:
        await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="HTML")
    except Exception:
        logging.exception("Failed to notify admin about cancellation")


async def update_schedule_channel_stub(work_date: str) -> None:
    """Заглушка оновлення поста розкладу в каналі."""
    logging.info("Schedule channel refresh requested for %s (stub)", work_date)

from __future__ import annotations

import logging
from html import escape

from aiogram import Bot
from aiogram.types import User

from config import ADMIN_ID

logger = logging.getLogger(__name__)


def _safe(value: object) -> str:
    if value is None:
        return "-"
    return escape(str(value))


def _slot_hhmm(value: object) -> str:
    text = str(value or "")
    return escape(text[:5]) if text else "-"


def _username(telegram_user: User | None) -> str:
    if not telegram_user:
        return "-"
    if telegram_user.username:
        return f"@{escape(telegram_user.username)}"
    return "без username"


def _user_id(booking: dict, telegram_user: User | None) -> str:
    if telegram_user:
        return f"<code>{telegram_user.id}</code>"
    if booking.get("user_id") is not None:
        return f"<code>{escape(str(booking['user_id']))}</code>"
    return "-"


def _booking_lines(booking: dict, telegram_user: User | None) -> str:
    return (
        f"👤 <b>Клієнт:</b> {_safe(booking.get('client_name'))}\n"
        f"📞 <b>Телефон:</b> {_safe(booking.get('client_phone'))}\n"
        f"📅 <b>Дата:</b> {_safe(booking.get('work_date'))}\n"
        f"🕒 <b>Час:</b> {_slot_hhmm(booking.get('slot_time'))}\n"
        f"🆔 <b>User ID:</b> {_user_id(booking, telegram_user)}\n"
        f"🔗 <b>Username:</b> {_username(telegram_user)}"
    )


async def notify_admin_new_booking(
    bot: Bot,
    booking: dict,
    telegram_user: User | None = None,
) -> None:
    text = "✅ <b>Новий запис</b>\n\n" + _booking_lines(booking, telegram_user)
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="HTML")
    except Exception:
        logger.exception("Failed to notify admin about new booking")


async def notify_admin_cancelled(
    bot: Bot,
    booking: dict,
    cancelled_by: str,
    telegram_user: User | None = None,
) -> None:
    reason_title = {
        "by_user": "❌ <b>Запис скасовано користувачем</b>",
        "by_admin": "⚠️ <b>Запис скасовано адміністратором</b>",
    }.get(cancelled_by, "⚠️ <b>Запис скасовано</b>")

    text = reason_title + "\n\n" + _booking_lines(booking, telegram_user)
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="HTML")
    except Exception:
        logger.exception("Failed to notify admin about cancelled booking")

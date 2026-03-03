from __future__ import annotations

import logging
from datetime import date
from urllib.parse import urlparse

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatIdUnion

from app.database import SchedulePostNotFoundError, repo_days, repo_schedule_posts, repo_slots
from config import BOT_TOKEN, SCHEDULE_CHANNEL_ID

logger = logging.getLogger(__name__)

WEEKDAYS_RU = (
    "понеділок",
    "вівторок",
    "середа",
    "четвер",
    "п'ятниця",
    "субота",
    "неділя",
)


def _as_date(raw_date: date | str) -> date:
    if isinstance(raw_date, date):
        return raw_date
    return date.fromisoformat(str(raw_date))


def _normalize_chat_id(raw_chat_id: str) -> ChatIdUnion:
    value = (raw_chat_id or "").strip()
    if not value:
        return value

    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        if parsed.netloc in {"t.me", "www.t.me", "telegram.me", "www.telegram.me"}:
            value = parsed.path.strip("/").split("/")[0]

    if value.startswith("@"):
        return value

    if value.lstrip("-").isdigit():
        return int(value)

    return f"@{value}"


def _should_recreate_message(exc: TelegramBadRequest) -> bool:
    text = str(exc).lower()
    recreate_errors = (
        "message to edit not found",
        "message can't be edited",
        "message is not modified",
    )
    return any(marker in text for marker in recreate_errors)


def _slot_status(slot: dict, day_is_working: bool) -> str:
    if slot.get("booking_id"):
        return "🔴 зайнято"
    if not day_is_working:
        return "⚫ недоступно (день закрито)"
    if not slot.get("is_available", True):
        return "🟠 вимкнено"
    return "🟢 вільно"


async def render_day_schedule(raw_date: date | str) -> str:
    work_date = _as_date(raw_date)
    day = await repo_days.get_day_by_date(work_date)
    slots = await repo_slots.get_all_slots_by_date(work_date)

    weekday_name = WEEKDAYS_RU[work_date.weekday()]
    header = f"<b>Розклад на {work_date:%d.%m.%Y} ({weekday_name})</b>"

    if not day:
        if not slots:
            return header + "\n\n⚪ День не налаштовано.\nСлотів немає."
        day_is_working = True
        day_status = "🟡 статус дня не задано"
    else:
        day_is_working = bool(day["is_working"])
        day_status = "🟢 день відкритий" if day_is_working else "⚫ день закритий"

    lines: list[str] = [header, "", f"Статус: {day_status}"]

    if not slots:
        lines.append("Слотів немає.")
        return "\n".join(lines)

    lines.append("")
    for slot in slots:
        slot_time = str(slot.get("slot_time", ""))[:5] or "--:--"
        status = _slot_status(slot, day_is_working)
        lines.append(f"• <b>{slot_time}</b> — {status}")

    return "\n".join(lines)


async def publish_or_update_day(raw_date: date | str) -> None:
    work_date = _as_date(raw_date)
    text = await render_day_schedule(work_date)
    chat_id = _normalize_chat_id(SCHEDULE_CHANNEL_ID)

    bot = Bot(token=BOT_TOKEN)
    try:
        existing_post = await repo_schedule_posts.get_schedule_post(work_date)
        message_id = existing_post["channel_message_id"] if existing_post else None

        if message_id:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=int(message_id),
                    text=text,
                    parse_mode="HTML",
                )
                try:
                    await repo_schedule_posts.update_message_id(work_date, int(message_id))
                except SchedulePostNotFoundError:
                    await repo_schedule_posts.save_schedule_post(work_date, int(message_id))
                return
            except TelegramBadRequest as exc:
                if not _should_recreate_message(exc):
                    raise
                logger.warning(
                    "Failed to edit schedule post for %s (message_id=%s): %s. Recreating message.",
                    work_date.isoformat(),
                    message_id,
                    exc,
                )

        message = await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
        await repo_schedule_posts.save_schedule_post(work_date, int(message.message_id))
    except Exception:
        logger.exception("Failed to publish or update schedule post for %s", work_date.isoformat())
    finally:
        await bot.session.close()

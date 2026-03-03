from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from app.database.db import get_db
from config import BOT_TOKEN, TIMEZONE

logger = logging.getLogger(__name__)

REMINDER_TYPE_24H = "24h"
REMINDER_STATUS_SCHEDULED = "scheduled"
REMINDER_STATUS_SENT = "sent"
REMINDER_STATUS_CANCELLED = "cancelled"

# Текст нагадування.
REMINDER_TEXT_TEMPLATE = (
    "Нагадуємо, що ви записані на нарощування вій завтра о {time}. \n"
    "Чекаємо на вас ️"
)

scheduler = AsyncIOScheduler(timezone=TIMEZONE)


def _tz() -> ZoneInfo:
    return ZoneInfo(TIMEZONE)


def _ensure_scheduler_started() -> None:
    if not scheduler.running:
        scheduler.start()


def _job_id_for_booking(booking_id: int) -> str:
    return f"reminder_booking_{booking_id}"


def _parse_visit_datetime(booking: dict) -> datetime:
    work_date = datetime.strptime(str(booking["work_date"]), "%Y-%m-%d").date()
    raw_time = str(booking["slot_time"])[:5]
    slot_time = datetime.strptime(raw_time, "%H:%M").time()
    return datetime.combine(work_date, slot_time, tzinfo=_tz())


async def _upsert_reminder(
    *,
    booking_id: int,
    remind_at: datetime,
    job_id: str,
    status: str,
    is_sent: bool,
) -> None:
    async with get_db() as db:
        now_iso = datetime.now(_tz()).isoformat()
        remind_at_iso = remind_at.isoformat()

        cursor = await db.execute(
            """
            UPDATE reminders
            SET scheduled_at = ?,
                remind_at = ?,
                job_id = ?,
                status = ?,
                is_sent = ?,
                sent_at = CASE WHEN ? = 1 THEN COALESCE(sent_at, ?) ELSE NULL END,
                cancelled_at = CASE WHEN ? = 'cancelled' THEN ? ELSE NULL END
            WHERE booking_id = ? AND reminder_type = ?
            """,
            (
                remind_at_iso,
                remind_at_iso,
                job_id,
                status,
                int(is_sent),
                int(is_sent),
                now_iso,
                status,
                now_iso,
                booking_id,
                REMINDER_TYPE_24H,
            ),
        )
        if cursor.rowcount == 0:
            await db.execute(
                """
                INSERT INTO reminders (
                    booking_id,
                    reminder_type,
                    scheduled_at,
                    remind_at,
                    job_id,
                    status,
                    is_sent,
                    sent_at,
                    cancelled_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    booking_id,
                    REMINDER_TYPE_24H,
                    remind_at_iso,
                    remind_at_iso,
                    job_id,
                    status,
                    int(is_sent),
                    now_iso if is_sent and status == REMINDER_STATUS_SENT else None,
                    now_iso if status == REMINDER_STATUS_CANCELLED else None,
                ),
            )
        await db.commit()


async def _mark_sent(booking_id: int) -> None:
    async with get_db() as db:
        now_iso = datetime.now(_tz()).isoformat()
        await db.execute(
            """
            UPDATE reminders
            SET status = ?, is_sent = 1, sent_at = ?, cancelled_at = NULL
            WHERE booking_id = ? AND reminder_type = ?
            """,
            (REMINDER_STATUS_SENT, now_iso, booking_id, REMINDER_TYPE_24H),
        )
        await db.commit()


async def _run_reminder_job(booking_id: int, user_id: int, visit_time: str) -> None:
    bot = Bot(BOT_TOKEN)
    try:
        text = REMINDER_TEXT_TEMPLATE.format(time=visit_time)
        await bot.send_message(chat_id=user_id, text=text)
        await _mark_sent(booking_id)
    except Exception:
        logger.exception("Failed to send reminder for booking_id=%s", booking_id)
    finally:
        await bot.session.close()


async def schedule_reminder_for_booking(booking: dict) -> None:
    booking_id = int(booking["id"])
    user_id = int(booking["user_id"])
    visit_dt = _parse_visit_datetime(booking)
    now = datetime.now(_tz())

    # Нагадування лише якщо до візиту більше 24 годин.
    if visit_dt <= now + timedelta(hours=24):
        logger.info("Skip 24h reminder for booking_id=%s: visit in <=24h", booking_id)
        return

    remind_at = visit_dt - timedelta(hours=24)
    job_id = _job_id_for_booking(booking_id)
    visit_time = visit_dt.strftime("%H:%M")

    _ensure_scheduler_started()
    scheduler.add_job(
        _run_reminder_job,
        trigger=DateTrigger(run_date=remind_at),
        id=job_id,
        replace_existing=True,
        kwargs={"booking_id": booking_id, "user_id": user_id, "visit_time": visit_time},
    )

    await _upsert_reminder(
        booking_id=booking_id,
        remind_at=remind_at,
        job_id=job_id,
        status=REMINDER_STATUS_SCHEDULED,
        is_sent=False,
    )


async def cancel_reminder(booking_id: int) -> None:
    job_id = _job_id_for_booking(int(booking_id))
    if scheduler.running:
        try:
            scheduler.remove_job(job_id)
        except JobLookupError:
            pass

    await _upsert_reminder(
        booking_id=int(booking_id),
        remind_at=datetime.now(_tz()),
        job_id=job_id,
        status=REMINDER_STATUS_CANCELLED,
        is_sent=True,
    )


async def restore_reminders_on_startup() -> None:
    _ensure_scheduler_started()
    now = datetime.now(_tz())
    restored = 0

    async with get_db() as db:
        async with db.execute(
            """
            SELECT
                r.booking_id,
                r.remind_at,
                r.job_id,
                b.user_id,
                ts.slot_time
            FROM reminders r
            JOIN bookings b ON b.id = r.booking_id
            JOIN time_slots ts ON ts.id = b.time_slot_id
            WHERE r.remind_at > ?
              AND COALESCE(r.status, 'scheduled') = 'scheduled'
              AND b.status = 'active'
            ORDER BY r.remind_at ASC
            """,
            (now.isoformat(),),
        ) as cursor:
            rows = await cursor.fetchall()

    for row in rows:
        booking_id = int(row[0])
        remind_at = datetime.fromisoformat(str(row[1]))
        job_id = str(row[2] or _job_id_for_booking(booking_id))
        user_id = int(row[3])
        visit_time = str(row[4])[:5]

        scheduler.add_job(
            _run_reminder_job,
            trigger=DateTrigger(run_date=remind_at),
            id=job_id,
            replace_existing=True,
            kwargs={"booking_id": booking_id, "user_id": user_id, "visit_time": visit_time},
        )
        restored += 1

    logger.info("Reminders restored on startup: %s", restored)

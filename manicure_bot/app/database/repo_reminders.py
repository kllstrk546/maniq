"""Репозиторій для роботи з нагадуваннями."""
from datetime import datetime
from typing import Optional

from app.database.db import get_db
from app.database.exceptions import ReminderNotFoundError


async def save_reminder(
    booking_id: int, 
    reminder_type: str, 
    scheduled_at: datetime
) -> int:
    """Зберегти нове нагадування.
    
    Args:
        booking_id: ID бронювання
        reminder_type: Тип нагадування ('24h', '2h', 'custom')
        scheduled_at: Час, коли відправити нагадування
    
    Returns:
        ID створеного нагадування
    """
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO reminders (booking_id, reminder_type, scheduled_at, is_sent) 
               VALUES (?, ?, ?, 0)""",
            (booking_id, reminder_type, scheduled_at.isoformat())
        )
        await db.commit()
        return cursor.lastrowid


async def update_reminder(
    reminder_id: int, 
    scheduled_at: datetime
) -> None:
    """Оновити час нагадування.
    
    Args:
        reminder_id: ID нагадування
        scheduled_at: Новий час відправки
    
    Raises:
        ReminderNotFoundError: Якщо нагадування не знайдено
    """
    async with get_db() as db:
        cursor = await db.execute(
            """UPDATE reminders 
               SET scheduled_at = ?, is_sent = 0, sent_at = NULL 
               WHERE id = ?""",
            (scheduled_at.isoformat(), reminder_id)
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise ReminderNotFoundError(f"Нагадування з ID {reminder_id} не знайдено")


async def get_scheduled_reminders(
    before: datetime, 
    is_sent: bool = False
) -> list[dict]:
    """Отримати заплановані нагадування для обробки.
    
    Args:
        before: Верхня межа часу (нагадування до цього часу)
        is_sent: Фільтр за статусом відправки
    
    Returns:
        Список нагадувань із даними бронювання
    """
    async with get_db() as db:
        async with db.execute(
            """SELECT r.id, r.booking_id, r.reminder_type, r.scheduled_at, r.is_sent,
                      b.user_id, b.time_slot_id, ts.slot_time, wd.work_date
               FROM reminders r
               JOIN bookings b ON r.booking_id = b.id
               JOIN time_slots ts ON b.time_slot_id = ts.id
               JOIN work_days wd ON ts.work_day_id = wd.id
               WHERE r.scheduled_at <= ? AND r.is_sent = ?
               ORDER BY r.scheduled_at""",
            (before.isoformat(), is_sent)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "booking_id": row[1],
                    "reminder_type": row[2],
                    "scheduled_at": row[3],
                    "is_sent": bool(row[4]),
                    "user_id": row[5],
                    "time_slot_id": row[6],
                    "slot_time": row[7],
                    "work_date": row[8]
                }
                for row in rows
            ]


async def mark_sent(reminder_id: int) -> None:
    """Позначити нагадування як відправлене.
    
    Args:
        reminder_id: ID нагадування
    
    Raises:
        ReminderNotFoundError: Якщо нагадування не знайдено
    """
    async with get_db() as db:
        cursor = await db.execute(
            """UPDATE reminders 
               SET is_sent = 1, sent_at = ? 
               WHERE id = ?""",
            (datetime.now().isoformat(), reminder_id)
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise ReminderNotFoundError(f"Нагадування з ID {reminder_id} не знайдено")


async def mark_cancelled(reminder_id: int) -> None:
    """Скасувати нагадування (позначити як відправлене без фактичної відправки).
    
    Використовується під час скасування бронювання.
    
    Args:
        reminder_id: ID нагадування
    
    Raises:
        ReminderNotFoundError: Якщо нагадування не знайдено
    """
    async with get_db() as db:
        cursor = await db.execute(
            """UPDATE reminders 
               SET is_sent = 1 
               WHERE id = ? AND is_sent = 0""",
            (reminder_id,)
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise ReminderNotFoundError(f"Нагадування з ID {reminder_id} не знайдено або вже відправлено")


async def cancel_reminders_for_booking(booking_id: int) -> int:
    """Скасувати всі невідправлені нагадування для бронювання.
    
    Args:
        booking_id: ID бронювання
    
    Returns:
        Кількість скасованих нагадувань
    """
    async with get_db() as db:
        cursor = await db.execute(
            """UPDATE reminders 
               SET is_sent = 1 
               WHERE booking_id = ? AND is_sent = 0""",
            (booking_id,)
        )
        await db.commit()
        return cursor.rowcount


async def get_reminder(reminder_id: int) -> Optional[dict]:
    """Отримати нагадування за ID.
    
    Returns:
        Словник із даними нагадування або None
    """
    async with get_db() as db:
        async with db.execute(
            """SELECT r.id, r.booking_id, r.reminder_type, r.scheduled_at, 
                      r.sent_at, r.is_sent, r.created_at
               FROM reminders r
               WHERE r.id = ?""",
            (reminder_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "booking_id": row[1],
                    "reminder_type": row[2],
                    "scheduled_at": row[3],
                    "sent_at": row[4],
                    "is_sent": bool(row[5]),
                    "created_at": row[6]
                }
            return None


async def get_pending_reminders_count() -> int:
    """Отримати кількість нагадувань, що очікують на відправку.
    
    Returns:
        Кількість невідправлених нагадувань
    """
    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM reminders WHERE is_sent = 0"
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

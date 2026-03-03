"""Repository for time slots."""

from __future__ import annotations

import logging
from datetime import date, time
from typing import Optional

import aiosqlite

from app.database.db import get_db
from app.database.exceptions import (
    SlotAlreadyExistsError,
    SlotHasBookingError,
    SlotNotFoundError,
)

logger = logging.getLogger(__name__)


async def _refresh_schedule_for_date(work_date_raw: str | date) -> None:
    try:
        from app.services.schedule_channel_service import publish_or_update_day

        work_date = date.fromisoformat(work_date_raw) if isinstance(work_date_raw, str) else work_date_raw
        await publish_or_update_day(work_date)
    except Exception:
        logger.exception("Failed to refresh schedule channel for date %s", work_date_raw)


async def add_slot(work_day_id: int, slot_time: time) -> int:
    """Add a slot to a work day."""
    async with get_db() as db:
        try:
            cursor = await db.execute(
                """INSERT INTO time_slots (work_day_id, slot_time, is_available)
                   VALUES (?, ?, 1)""",
                (work_day_id, slot_time.isoformat()),
            )
            await db.commit()

            async with db.execute(
                "SELECT work_date FROM work_days WHERE id = ?",
                (work_day_id,),
            ) as day_cursor:
                day_row = await day_cursor.fetchone()
            if day_row:
                await _refresh_schedule_for_date(day_row[0])

            return int(cursor.lastrowid)
        except aiosqlite.IntegrityError as exc:
            raise SlotAlreadyExistsError(
                f"Слот на {slot_time} для дня {work_day_id} вже існує"
            ) from exc


async def get_slot(slot_id: int) -> Optional[dict]:
    """Get slot by ID."""
    async with get_db() as db:
        async with db.execute(
            """SELECT ts.id, ts.work_day_id, ts.slot_time, ts.is_available, ts.created_at,
                      wd.work_date
               FROM time_slots ts
               JOIN work_days wd ON ts.work_day_id = wd.id
               WHERE ts.id = ?""",
            (slot_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "work_day_id": row[1],
                    "slot_time": row[2],
                    "is_available": bool(row[3]),
                    "created_at": row[4],
                    "work_date": row[5],
                }
            return None


async def delete_slot(slot_id: int) -> None:
    """Delete slot if it has no active booking."""
    async with get_db() as db:
        async with db.execute(
            """SELECT wd.work_date
               FROM time_slots ts
               JOIN work_days wd ON wd.id = ts.work_day_id
               WHERE ts.id = ?""",
            (slot_id,),
        ) as day_cursor:
            day_row = await day_cursor.fetchone()
        if not day_row:
            raise SlotNotFoundError(f"Слот з ID {slot_id} не знайдено")

        async with db.execute(
            """SELECT COUNT(*) FROM bookings
               WHERE time_slot_id = ? AND status = 'active'""",
            (slot_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0] > 0:
                raise SlotHasBookingError(
                    f"Неможливо видалити слот {slot_id}: є активне бронювання"
                )

        cursor = await db.execute("DELETE FROM time_slots WHERE id = ?", (slot_id,))
        await db.commit()
        if cursor.rowcount == 0:
            raise SlotNotFoundError(f"Слот з ID {slot_id} не знайдено")

        await _refresh_schedule_for_date(day_row[0])


async def set_available(slot_id: int, is_available: bool) -> None:
    """Set slot availability."""
    async with get_db() as db:
        cursor = await db.execute(
            "UPDATE time_slots SET is_available = ? WHERE id = ?",
            (is_available, slot_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise SlotNotFoundError(f"Слот з ID {slot_id} не знайдено")


async def get_free_slots_by_date(work_date: date) -> list[dict]:
    """Get free slots by date."""
    async with get_db() as db:
        async with db.execute(
            """SELECT ts.id, ts.work_day_id, ts.slot_time, ts.created_at
               FROM time_slots ts
               JOIN work_days wd ON ts.work_day_id = wd.id
               WHERE wd.work_date = ? AND ts.is_available = 1
               AND NOT EXISTS (
                   SELECT 1 FROM bookings b
                   WHERE b.time_slot_id = ts.id AND b.status = 'active'
               )
               ORDER BY ts.slot_time""",
            (work_date.isoformat(),),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "work_day_id": row[1],
                    "slot_time": row[2],
                    "created_at": row[3],
                }
                for row in rows
            ]


async def get_free_slot_counts_by_date(start_date: date, end_date: date) -> dict[str, int]:
    """Return free slot counts grouped by work date in [start_date, end_date]."""
    async with get_db() as db:
        async with db.execute(
            """
            SELECT wd.work_date, COUNT(ts.id) AS free_count
            FROM work_days wd
            JOIN time_slots ts ON ts.work_day_id = wd.id
            LEFT JOIN bookings b
                ON b.time_slot_id = ts.id
               AND b.status = 'active'
            WHERE wd.work_date BETWEEN ? AND ?
              AND wd.is_working = 1
              AND ts.is_available = 1
              AND b.id IS NULL
            GROUP BY wd.work_date
            ORDER BY wd.work_date
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ) as cursor:
            rows = await cursor.fetchall()
            return {str(row[0]): int(row[1]) for row in rows}


async def get_nearest_free_date(start_date: date, end_date: date) -> date | None:
    """Return nearest date with at least one free slot in [start_date, end_date]."""
    async with get_db() as db:
        async with db.execute(
            """
            SELECT wd.work_date
            FROM work_days wd
            JOIN time_slots ts ON ts.work_day_id = wd.id
            LEFT JOIN bookings b
                ON b.time_slot_id = ts.id
               AND b.status = 'active'
            WHERE wd.work_date BETWEEN ? AND ?
              AND wd.is_working = 1
              AND ts.is_available = 1
              AND b.id IS NULL
            GROUP BY wd.work_date
            ORDER BY wd.work_date ASC
            LIMIT 1
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return date.fromisoformat(str(row[0]))


async def get_all_slots_by_date(work_date: date) -> list[dict]:
    """Get all slots by date with booking markers."""
    async with get_db() as db:
        async with db.execute(
            """SELECT ts.id, ts.work_day_id, ts.slot_time, ts.is_available, ts.created_at,
                      b.id as booking_id, b.user_id, b.status
               FROM time_slots ts
               JOIN work_days wd ON ts.work_day_id = wd.id
               LEFT JOIN bookings b ON ts.id = b.time_slot_id AND b.status = 'active'
               WHERE wd.work_date = ?
               ORDER BY ts.slot_time""",
            (work_date.isoformat(),),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "work_day_id": row[1],
                    "slot_time": row[2],
                    "is_available": bool(row[3]),
                    "created_at": row[4],
                    "booking_id": row[5],
                    "user_id": row[6],
                    "booking_status": row[7],
                }
                for row in rows
            ]


async def delete_all_slots_for_day(work_day_id: int) -> int:
    """Delete all slots for day when there are no active bookings."""
    async with get_db() as db:
        async with db.execute(
            """SELECT COUNT(*) FROM bookings b
               JOIN time_slots ts ON b.time_slot_id = ts.id
               WHERE ts.work_day_id = ? AND b.status = 'active'""",
            (work_day_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0] > 0:
                raise SlotHasBookingError(
                    f"Неможливо видалити всі слоти дня {work_day_id}: є активні бронювання"
                )

        async with db.execute(
            "SELECT work_date FROM work_days WHERE id = ?",
            (work_day_id,),
        ) as day_cursor:
            day_row = await day_cursor.fetchone()

        cursor = await db.execute(
            "DELETE FROM time_slots WHERE work_day_id = ?",
            (work_day_id,),
        )
        await db.commit()

        if day_row:
            await _refresh_schedule_for_date(day_row[0])

        return cursor.rowcount

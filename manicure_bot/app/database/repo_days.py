"""Repository for work days."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import aiosqlite

from app.database.db import get_db
from app.database.exceptions import DayAlreadyExistsError, DayNotFoundError

logger = logging.getLogger(__name__)


async def _refresh_schedule_for_date(work_date_raw: str | date) -> None:
    try:
        from app.services.schedule_channel_service import publish_or_update_day

        work_date = date.fromisoformat(work_date_raw) if isinstance(work_date_raw, str) else work_date_raw
        await publish_or_update_day(work_date)
    except Exception:
        logger.exception("Failed to refresh schedule channel for date %s", work_date_raw)


async def create_day(work_date: date, is_working: bool = True) -> int:
    """Create work day."""
    async with get_db() as db:
        try:
            cursor = await db.execute(
                "INSERT INTO work_days (work_date, is_working) VALUES (?, ?)",
                (work_date.isoformat(), is_working),
            )
            await db.commit()
            return int(cursor.lastrowid)
        except aiosqlite.IntegrityError as exc:
            raise DayAlreadyExistsError(f"День {work_date} вже існує") from exc


async def get_day(day_id: int) -> Optional[dict]:
    """Get day by ID."""
    async with get_db() as db:
        async with db.execute(
            "SELECT id, work_date, is_working, created_at FROM work_days WHERE id = ?",
            (day_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "work_date": row[1],
                    "is_working": bool(row[2]),
                    "created_at": row[3],
                }
            return None


async def get_day_by_date(work_date: date) -> Optional[dict]:
    """Get day by date."""
    async with get_db() as db:
        async with db.execute(
            "SELECT id, work_date, is_working, created_at FROM work_days WHERE work_date = ?",
            (work_date.isoformat(),),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "work_date": row[1],
                    "is_working": bool(row[2]),
                    "created_at": row[3],
                }
            return None


async def open_day(day_id: int) -> None:
    """Open day for bookings (is_working=True)."""
    async with get_db() as db:
        async with db.execute(
            "SELECT work_date FROM work_days WHERE id = ?",
            (day_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise DayNotFoundError(f"День з ID {day_id} не знайдено")

        await db.execute("UPDATE work_days SET is_working = 1 WHERE id = ?", (day_id,))
        await db.commit()

        await _refresh_schedule_for_date(row[0])


async def close_day(day_id: int) -> None:
    """Close day for bookings (is_working=False)."""
    async with get_db() as db:
        async with db.execute(
            "SELECT work_date FROM work_days WHERE id = ?",
            (day_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise DayNotFoundError(f"День з ID {day_id} не знайдено")

        await db.execute("UPDATE work_days SET is_working = 0 WHERE id = ?", (day_id,))
        await db.commit()

        await _refresh_schedule_for_date(row[0])


async def get_days_in_range(start_date: date, end_date: date) -> list[dict]:
    """Get days in date range."""
    async with get_db() as db:
        async with db.execute(
            """SELECT id, work_date, is_working, created_at
               FROM work_days
               WHERE work_date BETWEEN ? AND ?
               ORDER BY work_date""",
            (start_date.isoformat(), end_date.isoformat()),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "work_date": row[1],
                    "is_working": bool(row[2]),
                    "created_at": row[3],
                }
                for row in rows
            ]


async def get_day_status(work_date: date) -> Optional[bool]:
    """Get day status by date."""
    async with get_db() as db:
        async with db.execute(
            "SELECT is_working FROM work_days WHERE work_date = ?",
            (work_date.isoformat(),),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return bool(row[0])
            return None


async def delete_day(day_id: int) -> None:
    """Delete day (slots and bookings are deleted by cascade)."""
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM work_days WHERE id = ?", (day_id,))
        await db.commit()
        if cursor.rowcount == 0:
            raise DayNotFoundError(f"День з ID {day_id} не знайдено")

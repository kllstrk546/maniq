from __future__ import annotations

import aiosqlite

from app.database import BookingAlreadyExistsError, SlotNotAvailableError
from app.database.db import get_db
from app.database import repo_bookings


async def get_active_booking_for_user(user_id: int) -> dict | None:
    return await repo_bookings.get_active_booking_by_user(user_id)


async def user_has_active_booking(user_id: int) -> bool:
    booking = await get_active_booking_for_user(user_id)
    return booking is not None


async def get_slot_brief(slot_id: int) -> dict | None:
    async with get_db() as db:
        async with db.execute(
            """
            SELECT ts.id, ts.slot_time, wd.work_date, ts.is_available,
                   EXISTS(
                       SELECT 1 FROM bookings b
                       WHERE b.time_slot_id = ts.id AND b.status = 'active'
                   ) AS has_active_booking
            FROM time_slots ts
            JOIN work_days wd ON wd.id = ts.work_day_id
            WHERE ts.id = ?
            """,
            (slot_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "slot_time": row[1],
                "work_date": row[2],
                "is_available": bool(row[3]) and not bool(row[4]),
            }


async def create_booking_transactional(
    *,
    user_id: int,
    time_slot_id: int,
    client_name: str,
    client_phone: str,
) -> int:
    async with get_db() as db:
        try:
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                "SELECT 1 FROM bookings WHERE user_id = ? AND status = 'active' LIMIT 1",
                (user_id,),
            ) as cursor:
                if await cursor.fetchone():
                    raise BookingAlreadyExistsError("User already has active booking")

            slot_cursor = await db.execute(
                "UPDATE time_slots SET is_available = 0 WHERE id = ? AND is_available = 1",
                (time_slot_id,),
            )
            if slot_cursor.rowcount == 0:
                raise SlotNotAvailableError("Slot is already occupied")

            booking_cursor = await db.execute(
                """
                INSERT INTO bookings (user_id, time_slot_id, client_name, client_phone, status)
                VALUES (?, ?, ?, ?, 'active')
                """,
                (user_id, time_slot_id, client_name, client_phone),
            )

            await db.commit()
            return int(booking_cursor.lastrowid)
        except (BookingAlreadyExistsError, SlotNotAvailableError):
            await db.rollback()
            raise
        except aiosqlite.IntegrityError as exc:
            await db.rollback()
            message = str(exc)
            if "idx_unique_active_booking_per_slot" in message:
                raise SlotNotAvailableError("Slot is already occupied") from exc
            if "idx_unique_active_booking_per_user" in message:
                raise BookingAlreadyExistsError("User already has active booking") from exc
            raise
        except Exception:
            await db.rollback()
            raise


async def reschedule_booking_transactional(
    *,
    booking_id: int,
    user_id: int,
    new_time_slot_id: int,
) -> dict | None:
    return await repo_bookings.reschedule_booking_by_user(
        booking_id=booking_id,
        user_id=user_id,
        new_time_slot_id=new_time_slot_id,
    )

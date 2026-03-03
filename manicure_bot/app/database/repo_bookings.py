"""Репозиторій для роботи з бронюваннями."""
from datetime import date, datetime
from typing import Optional

import aiosqlite

from app.database.db import get_db
from app.database.exceptions import (
    BookingAlreadyExistsError,
    BookingNotFoundError,
    SlotNotAvailableError,
)


async def create_booking(user_id: int, time_slot_id: int) -> int:
    """Створити бронювання транзакційно.
    
    Перевіряє:
    - Доступність слота
    - Відсутність активного бронювання у користувача
    
    Args:
        user_id: ID користувача Telegram
        time_slot_id: ID часового слота
    
    Returns:
        ID створеного бронювання
    
    Raises:
        SlotNotAvailableError: Якщо слот недоступний або зайнятий
        BookingAlreadyExistsError: Якщо в користувача вже є активне бронювання
    """
    async with get_db() as db:
        # Перевіряємо доступність слота
        async with db.execute(
            """SELECT is_available FROM time_slots 
               WHERE id = ? AND is_available = 1""",
            (time_slot_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                raise SlotNotAvailableError(f"Слот {time_slot_id} недоступний")
        
        # Перевіряємо, чи немає вже бронювання на цей слот (про всяк випадок, partial unique index має відловити)
        async with db.execute(
            """SELECT COUNT(*) FROM bookings 
               WHERE time_slot_id = ? AND status = 'active'""",
            (time_slot_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0] > 0:
                raise SlotNotAvailableError(f"Слот {time_slot_id} вже зайнятий")
        
        # Перевіряємо, чи немає в користувача активного бронювання (partial unique index має відловити)
        async with db.execute(
            """SELECT COUNT(*) FROM bookings 
               WHERE user_id = ? AND status = 'active'""",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0] > 0:
                raise BookingAlreadyExistsError(
                    f"У користувача {user_id} вже є активне бронювання"
                )
        
        try:
            # Створюємо бронювання
            cursor = await db.execute(
                """INSERT INTO bookings (user_id, time_slot_id, status) 
                   VALUES (?, ?, 'active')""",
                (user_id, time_slot_id)
            )
            booking_id = cursor.lastrowid
            await db.commit()
            return booking_id
        except aiosqlite.IntegrityError as e:
            # Обробляємо можливі порушення unique constraints
            if "idx_unique_active_booking_per_slot" in str(e):
                raise SlotNotAvailableError(f"Слот {time_slot_id} вже зайнятий")
            if "idx_unique_active_booking_per_user" in str(e):
                raise BookingAlreadyExistsError(
                    f"У користувача {user_id} вже є активне бронювання"
                )
            raise


async def get_booking(booking_id: int) -> Optional[dict]:
    """Отримати бронювання за ID.
    
    Returns:
        Словник із даними бронювання або None
    """
    async with get_db() as db:
        async with db.execute(
            """SELECT b.id, b.user_id, b.time_slot_id, b.status, b.created_at, b.cancelled_at,
                      ts.slot_time, wd.work_date
               FROM bookings b
               JOIN time_slots ts ON b.time_slot_id = ts.id
               JOIN work_days wd ON ts.work_day_id = wd.id
               WHERE b.id = ?""",
            (booking_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "user_id": row[1],
                    "time_slot_id": row[2],
                    "status": row[3],
                    "created_at": row[4],
                    "cancelled_at": row[5],
                    "slot_time": row[6],
                    "work_date": row[7]
                }
            return None


async def get_active_booking_by_user(user_id: int) -> Optional[dict]:
    """Отримати активне бронювання користувача.
    
    Returns:
        Словник із даними бронювання або None
    """
    async with get_db() as db:
        async with db.execute(
            """SELECT b.id, b.user_id, b.time_slot_id, b.status, b.created_at,
                      b.client_name, b.client_phone, ts.slot_time, wd.work_date
               FROM bookings b
               JOIN time_slots ts ON b.time_slot_id = ts.id
               JOIN work_days wd ON ts.work_day_id = wd.id
               WHERE b.user_id = ? AND b.status = 'active'
               LIMIT 1""",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "user_id": row[1],
                    "time_slot_id": row[2],
                    "status": row[3],
                    "created_at": row[4],
                    "client_name": row[5],
                    "client_phone": row[6],
                    "slot_time": row[7],
                    "work_date": row[8]
                }
            return None


async def cancel_booking_by_user(booking_id: int, user_id: int) -> Optional[dict]:
    """Скасувати активний запис користувача транзакційно.

    Виконує в одній транзакції:
    - booking.status = cancelled_by_user
    - звільняє слот (is_available = 1)
    - скасовує невідправлені нагадування (is_sent = 1)

    Returns:
        Словник із даними скасованого запису або None, якщо запис не знайдено/не активний.
    """
    async with get_db() as db:
        try:
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                """SELECT b.id, b.time_slot_id, b.client_name, b.client_phone,
                          ts.slot_time, wd.work_date
                   FROM bookings b
                   JOIN time_slots ts ON ts.id = b.time_slot_id
                   JOIN work_days wd ON wd.id = ts.work_day_id
                   WHERE b.id = ? AND b.user_id = ? AND b.status = 'active'
                   LIMIT 1""",
                (booking_id, user_id),
            ) as cursor:
                row = await cursor.fetchone()

            if not row:
                await db.rollback()
                return None

            cancelled_at = datetime.now().isoformat()
            booking_cursor = await db.execute(
                """UPDATE bookings
                   SET status = 'cancelled_by_user', cancelled_at = ?
                   WHERE id = ? AND user_id = ? AND status = 'active'""",
                (cancelled_at, booking_id, user_id),
            )
            if booking_cursor.rowcount == 0:
                await db.rollback()
                return None

            await db.execute(
                "UPDATE time_slots SET is_available = 1 WHERE id = ?",
                (row[1],),
            )

            reminders_cursor = await db.execute(
                """UPDATE reminders
                   SET is_sent = 1
                   WHERE booking_id = ? AND is_sent = 0""",
                (booking_id,),
            )

            await db.commit()
            return {
                "id": row[0],
                "time_slot_id": row[1],
                "client_name": row[2],
                "client_phone": row[3],
                "slot_time": row[4],
                "work_date": row[5],
                "cancelled_at": cancelled_at,
                "cancelled_reminders": reminders_cursor.rowcount,
                "status": "cancelled_by_user",
            }
        except Exception:
            await db.rollback()
            raise


async def reschedule_booking_by_user(
    booking_id: int,
    user_id: int,
    new_time_slot_id: int,
) -> Optional[dict]:
    """Перенести активний запис користувача на інший часовий слот транзакційно."""
    async with get_db() as db:
        try:
            await db.execute("BEGIN IMMEDIATE")

            async with db.execute(
                """
                SELECT b.id, b.user_id, b.time_slot_id, b.client_name, b.client_phone,
                       ts.slot_time, wd.work_date
                FROM bookings b
                JOIN time_slots ts ON ts.id = b.time_slot_id
                JOIN work_days wd ON wd.id = ts.work_day_id
                WHERE b.id = ? AND b.user_id = ? AND b.status = 'active'
                LIMIT 1
                """,
                (booking_id, user_id),
            ) as cursor:
                current = await cursor.fetchone()

            if not current:
                await db.rollback()
                return None

            old_slot_id = int(current[2])
            if old_slot_id == int(new_time_slot_id):
                await db.rollback()
                raise SlotNotAvailableError("Новий слот збігається з поточним")

            async with db.execute(
                """
                SELECT ts.id, ts.slot_time, wd.work_date, wd.is_working, ts.is_available,
                       EXISTS(
                           SELECT 1 FROM bookings b
                           WHERE b.time_slot_id = ts.id AND b.status = 'active'
                       ) AS has_active_booking
                FROM time_slots ts
                JOIN work_days wd ON wd.id = ts.work_day_id
                WHERE ts.id = ?
                LIMIT 1
                """,
                (new_time_slot_id,),
            ) as cursor:
                new_slot = await cursor.fetchone()

            if (
                not new_slot
                or not bool(new_slot[3])
                or not bool(new_slot[4])
                or bool(new_slot[5])
            ):
                await db.rollback()
                raise SlotNotAvailableError("Обраний слот недоступний")

            reserve_cursor = await db.execute(
                "UPDATE time_slots SET is_available = 0 WHERE id = ? AND is_available = 1",
                (new_time_slot_id,),
            )
            if reserve_cursor.rowcount == 0:
                await db.rollback()
                raise SlotNotAvailableError("Обраний слот вже зайнятий")

            await db.execute(
                "UPDATE time_slots SET is_available = 1 WHERE id = ?",
                (old_slot_id,),
            )

            booking_cursor = await db.execute(
                """
                UPDATE bookings
                SET time_slot_id = ?
                WHERE id = ? AND user_id = ? AND status = 'active'
                """,
                (new_time_slot_id, booking_id, user_id),
            )
            if booking_cursor.rowcount == 0:
                await db.rollback()
                return None

            await db.commit()
            return {
                "id": int(current[0]),
                "user_id": int(current[1]),
                "time_slot_id": int(new_slot[0]),
                "client_name": current[3],
                "client_phone": current[4],
                "old_slot_id": old_slot_id,
                "old_slot_time": current[5],
                "old_work_date": current[6],
                "slot_time": new_slot[1],
                "work_date": new_slot[2],
                "status": "active",
            }
        except SlotNotAvailableError:
            await db.rollback()
            raise
        except aiosqlite.IntegrityError as exc:
            await db.rollback()
            if "idx_unique_active_booking_per_slot" in str(exc):
                raise SlotNotAvailableError("Обраний слот вже зайнятий") from exc
            raise
        except Exception:
            await db.rollback()
            raise


async def cancel_booking(booking_id: int) -> None:
    """Скасувати бронювання.
    
    Args:
        booking_id: ID бронювання
    
    Raises:
        BookingNotFoundError: Якщо бронювання не знайдено
    """
    async with get_db() as db:
        cursor = await db.execute(
            """UPDATE bookings 
               SET status = 'cancelled', cancelled_at = ? 
               WHERE id = ? AND status = 'active'""",
            (datetime.now().isoformat(), booking_id)
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise BookingNotFoundError(
                f"Активне бронювання з ID {booking_id} не знайдено"
            )


async def complete_booking(booking_id: int) -> None:
    """Позначити бронювання як виконане.
    
    Args:
        booking_id: ID бронювання
    
    Raises:
        BookingNotFoundError: Якщо бронювання не знайдено
    """
    async with get_db() as db:
        cursor = await db.execute(
            """UPDATE bookings 
               SET status = 'completed' 
               WHERE id = ? AND status = 'active'""",
            (booking_id,)
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise BookingNotFoundError(
                f"Активне бронювання з ID {booking_id} не знайдено"
            )


async def get_bookings_by_date(work_date: date) -> list[dict]:
    """Отримати всі бронювання на конкретну дату.
    
    Returns:
        Список бронювань
    """
    async with get_db() as db:
        async with db.execute(
            """SELECT b.id, b.user_id, b.time_slot_id, b.status, b.created_at, b.cancelled_at,
                      ts.slot_time
               FROM bookings b
               JOIN time_slots ts ON b.time_slot_id = ts.id
               JOIN work_days wd ON ts.work_day_id = wd.id
               WHERE wd.work_date = ?
               ORDER BY ts.slot_time, b.created_at""",
            (work_date.isoformat(),)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "user_id": row[1],
                    "time_slot_id": row[2],
                    "status": row[3],
                    "created_at": row[4],
                    "cancelled_at": row[5],
                    "slot_time": row[6]
                }
                for row in rows
            ]


async def get_active_bookings_by_date(work_date: date) -> list[dict]:
    """Отримати лише активні бронювання на дату.
    
    Returns:
        Список активних бронювань
    """
    async with get_db() as db:
        async with db.execute(
            """SELECT b.id, b.user_id, b.time_slot_id, b.created_at,
                      b.client_name, b.client_phone,
                      ts.slot_time
               FROM bookings b
               JOIN time_slots ts ON b.time_slot_id = ts.id
               JOIN work_days wd ON ts.work_day_id = wd.id
               WHERE wd.work_date = ? AND b.status = 'active'
               ORDER BY ts.slot_time""",
            (work_date.isoformat(),)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "user_id": row[1],
                    "time_slot_id": row[2],
                    "created_at": row[3],
                    "client_name": row[4],
                    "client_phone": row[5],
                    "slot_time": row[6],
                }
                for row in rows
            ]

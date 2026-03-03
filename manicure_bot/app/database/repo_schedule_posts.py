"""Репозиторій для роботи з постами розкладу в каналі."""
from datetime import date, datetime
from typing import Optional

from app.database.db import get_db
from app.database.exceptions import SchedulePostNotFoundError


async def save_schedule_post(
    post_date: date, 
    channel_message_id: int
) -> int:
    """Зберегти пост розкладу.
    
    Args:
        post_date: Дата розкладу
        channel_message_id: ID повідомлення в каналі Telegram
    
    Returns:
        ID запису в базі
    """
    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO schedule_posts (post_date, channel_message_id, updated_at) 
               VALUES (?, ?, ?)
               ON CONFLICT(post_date) DO UPDATE SET 
                   channel_message_id = excluded.channel_message_id,
                   updated_at = excluded.updated_at""",
            (post_date.isoformat(), channel_message_id, datetime.now().isoformat())
        )
        await db.commit()
        return cursor.lastrowid if cursor.lastrowid else cursor.rowcount


async def get_schedule_post(post_date: date) -> Optional[dict]:
    """Отримати пост розкладу за датою.
    
    Returns:
        Словник із даними поста або None
    """
    async with get_db() as db:
        async with db.execute(
            """SELECT id, post_date, channel_message_id, created_at, updated_at
               FROM schedule_posts
               WHERE post_date = ?""",
            (post_date.isoformat(),)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "post_date": row[1],
                    "channel_message_id": row[2],
                    "created_at": row[3],
                    "updated_at": row[4]
                }
            return None


async def get_schedule_post_by_id(post_id: int) -> Optional[dict]:
    """Отримати пост розкладу за ID.
    
    Returns:
        Словник із даними поста або None
    """
    async with get_db() as db:
        async with db.execute(
            """SELECT id, post_date, channel_message_id, created_at, updated_at
               FROM schedule_posts
               WHERE id = ?""",
            (post_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "post_date": row[1],
                    "channel_message_id": row[2],
                    "created_at": row[3],
                    "updated_at": row[4]
                }
            return None


async def update_message_id(post_date: date, channel_message_id: int) -> None:
    """Оновити ID повідомлення в каналі.
    
    Args:
        post_date: Дата розкладу
        channel_message_id: Новий ID повідомлення
    
    Raises:
        SchedulePostNotFoundError: Якщо пост не знайдено
    """
    async with get_db() as db:
        cursor = await db.execute(
            """UPDATE schedule_posts 
               SET channel_message_id = ?, updated_at = ? 
               WHERE post_date = ?""",
            (channel_message_id, datetime.now().isoformat(), post_date.isoformat())
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise SchedulePostNotFoundError(f"Пост на дату {post_date} не знайдено")


async def delete_schedule_post(post_date: date) -> None:
    """Видалити пост розкладу.
    
    Args:
        post_date: Дата розкладу
    
    Raises:
        SchedulePostNotFoundError: Якщо пост не знайдено
    """
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM schedule_posts WHERE post_date = ?",
            (post_date.isoformat(),)
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise SchedulePostNotFoundError(f"Пост на дату {post_date} не знайдено")


async def get_posts_in_range(start_date: date, end_date: date) -> list[dict]:
    """Отримати пости розкладу в діапазоні дат.
    
    Args:
        start_date: Початкова дата
        end_date: Кінцева дата (включно)
    
    Returns:
        Список постів
    """
    async with get_db() as db:
        async with db.execute(
            """SELECT id, post_date, channel_message_id, created_at, updated_at
               FROM schedule_posts
               WHERE post_date BETWEEN ? AND ?
               ORDER BY post_date""",
            (start_date.isoformat(), end_date.isoformat())
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "post_date": row[1],
                    "channel_message_id": row[2],
                    "created_at": row[3],
                    "updated_at": row[4]
                }
                for row in rows
            ]

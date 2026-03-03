from __future__ import annotations

from datetime import datetime

from app.database.db import get_db

PRICES_TEXT_KEY = "prices_text_html"
PORTFOLIO_URL_KEY = "portfolio_url"

DEFAULT_PRICES_TEXT = "Френч — 1000₽\nКвадрат — 500₽"
DEFAULT_PORTFOLIO_URL = "https://ru.pinterest.com/crystalwithluv/_created/"


async def get_setting(key: str, default: str) -> str:
    async with get_db() as db:
        async with db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0] is not None:
                return str(row[0])
            return default


async def set_setting(key: str, value: str) -> None:
    async with get_db() as db:
        now = datetime.now().isoformat()
        await db.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value, now),
        )
        await db.commit()


async def get_prices_text() -> str:
    return await get_setting(PRICES_TEXT_KEY, DEFAULT_PRICES_TEXT)


async def set_prices_text(value: str) -> None:
    await set_setting(PRICES_TEXT_KEY, value)


async def get_portfolio_url() -> str:
    return await get_setting(PORTFOLIO_URL_KEY, DEFAULT_PORTFOLIO_URL)


async def set_portfolio_url(value: str) -> None:
    await set_setting(PORTFOLIO_URL_KEY, value)

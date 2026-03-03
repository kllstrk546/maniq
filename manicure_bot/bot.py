import asyncio
import logging
import sys

from aiogram import Bot

from app.database.db import init_db
from app.handlers import admin, base, booking, cancel, errors, prices_portfolio
from app.loader import dp
from app.middlewares import CallbackSubscriptionMiddleware
from app.services import restore_reminders_on_startup
from config import BOT_TOKEN


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("apscheduler").setLevel(logging.INFO)


async def on_startup(bot: Bot) -> None:
    """Дії під час запуску бота."""
    logging.info("Ініціалізація бази даних...")
    await init_db()
    logging.info("База даних готова")

    await restore_reminders_on_startup()
    logging.info("Нагадування відновлено")

    # Перевірка підписки для callback-запитів, пов'язаних із записом.
    dp.callback_query.middleware(CallbackSubscriptionMiddleware())
    logging.info("Middleware перевірки підписки зареєстровано")


async def main() -> None:
    configure_logging()
    bot = Bot(token=BOT_TOKEN)
    await on_startup(bot)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

"""Клавіатура перевірки підписки."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import CHANNEL_LINK
from app.callbacks import MainMenuCB


def get_subscription_keyboard() -> InlineKeyboardMarkup:
    """Клавіатура для непідписаних користувачів."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Підписатися на канал",
                    url=CHANNEL_LINK
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Перевірити підписку",
                    callback_data=MainMenuCB(action="check_subscription").pack()
                )
            ]
        ]
    )

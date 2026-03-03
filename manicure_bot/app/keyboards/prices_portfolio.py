"""Клавіатури для прайсів і портфоліо."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.callbacks import CalendarCB, MainMenuCB


def get_prices_keyboard() -> InlineKeyboardMarkup:
    """Клавіатура прайсів із CTA на запис і кнопкою меню."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 Записатися",
                    callback_data=CalendarCB(action="pick").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 В меню",
                    callback_data=MainMenuCB(action="start").pack()
                )
            ]
        ]
    )


def get_portfolio_keyboard() -> InlineKeyboardMarkup:
    """Клавіатура портфоліо з кнопкою повернення."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ До меню",
                    callback_data=MainMenuCB(action="start").pack()
                )
            ]
        ]
    )

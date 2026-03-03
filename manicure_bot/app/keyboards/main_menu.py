"""Клавіатура головного меню."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.callbacks import MainMenuCB, CalendarCB


def get_main_menu_keyboard(user_id: int, admin_id: int) -> InlineKeyboardMarkup:
    """Головне меню користувача.
    
    Args:
        user_id: ID користувача Telegram
        admin_id: ID адміністратора з config
    """
    buttons = [
        [
            InlineKeyboardButton(
                text="📅 Записатися",
                callback_data=CalendarCB(action="pick").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Мій запис",
                callback_data=MainMenuCB(action="my_booking").pack()
            ),
            InlineKeyboardButton(
                text="❌ Скасувати запис",
                callback_data=MainMenuCB(action="cancel_booking").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="💰 Прайси",
                callback_data=MainMenuCB(action="prices").pack()
            ),
            InlineKeyboardButton(
                text="📸 Портфоліо",
                callback_data=MainMenuCB(action="portfolio").pack()
            )
        ],
    ]
    
    # Адмін-панель тільки для адміністратора
    if user_id == admin_id:
        buttons.append([
            InlineKeyboardButton(
                text="⚙️ Адмін-панель",
                callback_data=MainMenuCB(action="admin").pack()
            )
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Кнопка повернення в головне меню."""
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

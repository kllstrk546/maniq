"""Клавіатура адмін-панелі."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.callbacks import AdminCB, MainMenuCB


def get_admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Головне меню адмін-панелі з швидкими діями."""
    buttons = [
        [
            InlineKeyboardButton(
                text="➕ Додати слот",
                callback_data=AdminCB(action="add_slot").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="🔒 Закрити день",
                callback_data=AdminCB(action="close_day_select").pack()
            ),
            InlineKeyboardButton(
                text="📅 Розклад на дату",
                callback_data=AdminCB(action="view_schedule").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="👥 Записи на сьогодні",
                callback_data=AdminCB(action="today_bookings").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="🏠 В меню",
                callback_data=MainMenuCB(action="start").pack()
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_back_keyboard() -> InlineKeyboardMarkup:
    """Кнопка повернення в адмін-панель."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ Назад до адмін-панелі",
                    callback_data=AdminCB(action="back").pack()
                )
            ]
        ]
    )


def get_admin_days_keyboard() -> InlineKeyboardMarkup:
    """Клавіатура керування робочими днями."""
    buttons = [
        [
            InlineKeyboardButton(
                text="📆 Відкрити день",
                callback_data=AdminCB(action="open_day").pack()
            ),
            InlineKeyboardButton(
                text="🔒 Закрити день",
                callback_data=AdminCB(action="close_day_select").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="◀️ Назад до адмін-панелі",
                callback_data=AdminCB(action="back").pack()
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_slots_keyboard() -> InlineKeyboardMarkup:
    """Клавіатура керування слотами."""
    buttons = [
        [
            InlineKeyboardButton(
                text="➕ Додати слот",
                callback_data=AdminCB(action="add_slot").pack()
            ),
            InlineKeyboardButton(
                text="➖ Видалити слот",
                callback_data=AdminCB(action="delete_slot").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="◀️ Назад до адмін-панелі",
                callback_data=AdminCB(action="back").pack()
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

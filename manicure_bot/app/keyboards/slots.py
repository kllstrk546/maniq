"""Клавіатура вибору часового слота."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.callbacks import SlotCB, CalendarCB, MainMenuCB


def get_slots_keyboard(
    date_str: str,
    slots: list[dict],
    calendar_pick_action: str = "pick",
) -> InlineKeyboardMarkup:
    """Клавіатура з вільними слотами.
    
    Args:
        date_str: Дата у форматі YYYY-MM-DD
        slots: Список слотів [{"id": int, "slot_time": str}, ...]
    """
    buttons = []
    
    # Слоти по 2 в ряд
    row = []
    for slot in slots:
        time_str = slot["slot_time"][:5]  # HH:MM з HH:MM:SS
        time_token = time_str.replace(":", "")
        row.append(
            InlineKeyboardButton(
                text=f"🕐 {time_str}",
                callback_data=SlotCB(
                    action="book",
                    date=date_str,
                    time=time_token,
                    slot_id=slot["id"]
                ).pack()
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    # Навігація
    buttons.append([
        InlineKeyboardButton(
            text="◀️ Інша дата",
            callback_data=CalendarCB(action=calendar_pick_action).pack()
        ),
        InlineKeyboardButton(
            text="📋 До меню",
            callback_data=MainMenuCB(action="start").pack()
        ),
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_no_slots_keyboard(date_str: str) -> InlineKeyboardMarkup:
    """Клавіатура, коли немає вільних слотів."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Оновити",
                    callback_data=SlotCB(action="refresh", date=date_str, time="").pack()
                ),
                InlineKeyboardButton(
                    text="◀️ Інша дата",
                    callback_data=CalendarCB(action="pick").pack()
                ),
            ]
        ]
    )

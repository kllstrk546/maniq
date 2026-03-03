"""Фабрики CallbackData для aiogram 3."""
from aiogram.filters.callback_data import CallbackData


class MainMenuCB(CallbackData, prefix="m"):
    """Головне меню."""
    action: str  # start, schedule, my_booking, cancel, admin


class CalendarCB(CallbackData, prefix="c"):
    """Календар вибору дати.
    
    Формат: c:action:date (YYYY-MM-DD) або c:nav:year:month для навігації
    """
    action: str  # pick, nav, nearest, back
    date: str | None = None  # YYYY-MM-DD або None для навігації
    month: int | None = None  # для навігації
    year: int | None = None   # для навігації


class SlotCB(CallbackData, prefix="s"):
    """Вибір часового слота.
    
    Формат: s:action:date:time:slot_id
    """
    action: str  # book, back, refresh
    date: str  # YYYY-MM-DD
    time: str  # HH:MM
    slot_id: int | None = None  # ID слота в БД (для бронювання)


class BookingCB(CallbackData, prefix="b"):
    """Дії з бронюванням.
    
    Формат: b:action:booking_id
    """
    action: str  # confirm, cancel, details
    booking_id: int


class AdminCB(CallbackData, prefix="a"):
    """Адмін-панель.
    
    Універсальний callback для адмінських дій.
    """
    action: str  # days, slots, stats, broadcast, back
    date: str | None = None      # YYYY-MM-DD для роботи з конкретним днем
    slot_id: int | None = None   # ID слота
    booking_id: int | None = None  # ID бронювання


class DayAdminCB(CallbackData, prefix="d"):
    """Керування робочими днями.
    
    Формат: d:action:date або d:nav:year:month
    """
    action: str  # open, close, add_slots, delete, nav, back
    date: str | None = None   # YYYY-MM-DD
    month: int | None = None  # для навігації
    year: int | None = None   # для навігації


class SlotAdminCB(CallbackData, prefix="t"):
    """Керування слотами (t - time).
    
    Формат: t:action:date:time:slot_id
    """
    action: str  # add, delete, toggle, back
    date: str    # YYYY-MM-DD
    time: str | None = None   # HH:MM
    slot_id: int | None = None


class ConfirmCB(CallbackData, prefix="y"):
    """Підтвердження дій (y - yes/no).
    
    Формат: y:action:entity:entity_id
    """
    action: str  # confirm, cancel
    entity: str  # booking, day, slot, reminder
    entity_id: int

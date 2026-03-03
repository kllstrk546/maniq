"""Keyboards exports."""

from app.keyboards.main_menu import get_main_menu_keyboard, get_back_to_menu_keyboard
from app.keyboards.calendar import get_calendar_keyboard
from app.keyboards.slots import get_slots_keyboard, get_no_slots_keyboard
from app.keyboards.prices_portfolio import get_prices_keyboard, get_portfolio_keyboard
from app.keyboards.admin_menu import (
    get_admin_menu_keyboard,
    get_admin_back_keyboard,
    get_admin_days_keyboard,
    get_admin_slots_keyboard,
)
from app.keyboards.subscription import get_subscription_keyboard

__all__ = [
    "get_main_menu_keyboard",
    "get_back_to_menu_keyboard",
    "get_calendar_keyboard",
    "get_slots_keyboard",
    "get_no_slots_keyboard",
    "get_prices_keyboard",
    "get_portfolio_keyboard",
    "get_admin_menu_keyboard",
    "get_admin_back_keyboard",
    "get_admin_days_keyboard",
    "get_admin_slots_keyboard",
    "get_subscription_keyboard",
]

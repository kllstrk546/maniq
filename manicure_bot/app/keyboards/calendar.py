"""Клавіатура календаря для вибору дати."""
from datetime import date, timedelta
from calendar import monthrange

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.callbacks import CalendarCB, MainMenuCB


def get_calendar_keyboard(
    year: int | None = None,
    month: int | None = None,
    available_dates: list[date] | None = None
) -> InlineKeyboardMarkup:
    """Календар для вибору дати запису.
    
    Args:
        year: Рік для відображення
        month: Місяць для відображення
        available_dates: Список дат, доступних для запису
    """
    today = date.today()
    year = year or today.year
    month = month or today.month
    available_dates = available_dates or []
    
    # Заголовок з місяцем і роком
    month_names = [
        "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
        "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"
    ]
    
    keyboard = []
    
    # Заголовок
    keyboard.append([
        InlineKeyboardButton(
            text=f"{month_names[month-1]} {year}",
            callback_data="ignore"
        )
    ])
    
    # Дні тижня
    keyboard.append([
        InlineKeyboardButton(text=day, callback_data="ignore")
        for day in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    ])
    
    # Дні місяця
    _, days_in_month = monthrange(year, month)
    first_weekday = date(year, month, 1).weekday()  # 0=Monday
    
    current_row = []
    
    # Порожні кнопки на початку
    for _ in range(first_weekday):
        current_row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
    
    for day in range(1, days_in_month + 1):
        current_date = date(year, month, day)
        
        # Визначаємо текст кнопки
        if current_date in available_dates:
            text = f"✅{day:2d}"
        elif current_date < today:
            text = f"{day:2d}"
        else:
            text = f"·{day:2d}·"
        
        # Створюємо callback
        if current_date >= today and current_date in available_dates:
            callback_data = CalendarCB(
                action="pick",
                date=current_date.isoformat()
            ).pack()
        else:
            callback_data = "ignore"
        
        current_row.append(InlineKeyboardButton(text=text, callback_data=callback_data))
        
        if len(current_row) == 7:
            keyboard.append(current_row)
            current_row = []
    
    # Додаємо дні, що залишилися
    if current_row:
        while len(current_row) < 7:
            current_row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
        keyboard.append(current_row)
    
    # Навігація
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    keyboard.append([
        InlineKeyboardButton(
            text="◀️",
            callback_data=CalendarCB(action="nav", year=prev_year, month=prev_month).pack()
        ),
        InlineKeyboardButton(
            text="▶️",
            callback_data=CalendarCB(action="nav", year=next_year, month=next_month).pack()
        ),
    ])
    
    # Кнопка назад
    keyboard.append([
        InlineKeyboardButton(
            text="◀️ До меню",
            callback_data=MainMenuCB(action="start").pack()
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

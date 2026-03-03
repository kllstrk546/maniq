"""Сервіс генерації календаря для запису."""
from datetime import date, timedelta
from calendar import monthrange

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.callbacks import CalendarCB
from app.database import repo_days, repo_slots


async def generate_calendar_keyboard(
    year: int,
    month: int,
    today: date | None = None,
    pick_action: str = "pick",
    nav_action: str = "nav",
    nearest_action: str | None = "nearest",
) -> InlineKeyboardMarkup:
    """Генерує клавіатуру календаря з доступними днями.
    
    Навігація обмежена: сьогодні .. сьогодні+1 місяць
    Клікабельні лише дні: робочі, не закриті, є вільний слот
    
    Args:
        year: Рік для відображення
        month: Місяць для відображення
        today: Поточна дата (для обмеження навігації)
    
    Returns:
        InlineKeyboardMarkup з календарем
    """
    if today is None:
        today = date.today()
    
    # Визначаємо межі навігації
    min_date = today
    max_date = today + timedelta(days=30)  # приблизно 1 місяць
    
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
    
    # Отримуємо дні місяця з БД одним запитом
    month_start = date(year, month, 1)
    _, days_in_month = monthrange(year, month)
    month_end = date(year, month, days_in_month)

    work_days = await repo_days.get_days_in_range(month_start, month_end)
    work_days_dict = {wd["work_date"]: wd for wd in work_days}

    # Отримуємо кількість вільних слотів по датах одним запитом
    range_start = max(month_start, min_date)
    range_end = min(month_end, max_date)
    free_counts: dict[str, int] = {}
    if range_start <= range_end:
        free_counts = await repo_slots.get_free_slot_counts_by_date(range_start, range_end)
    
    # Дні місяця
    first_weekday = month_start.weekday()  # 0=Monday
    
    current_row = []
    
    # Порожні кнопки на початку
    for _ in range(first_weekday):
        current_row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
    
    for day in range(1, days_in_month + 1):
        current_date = date(year, month, day)
        date_str = current_date.isoformat()

        day_info = work_days_dict.get(date_str)
        is_working = bool(day_info and day_info["is_working"])
        has_free_slots = free_counts.get(date_str, 0) > 0
        is_clickable = min_date <= current_date <= max_date and is_working and has_free_slots

        if is_clickable:
            text = f"✅ {day:02d}"
            callback_data = CalendarCB(
                action=pick_action,
                date=date_str
            ).pack()
        elif current_date == today:
            text = f"• {day:02d}"
            callback_data = "ignore"
        else:
            text = f"{day:02d}"
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
    
    # Навігація (обмежена)
    nav_buttons = []
    
    # Кнопка назад (якщо не вийшли за min_date)
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    prev_date = date(prev_year, prev_month, 1)
    
    if prev_date >= min_date.replace(day=1):
        nav_buttons.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=CalendarCB(action=nav_action, year=prev_year, month=prev_month).pack()
            )
        )
    else:
        nav_buttons.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
    
    # Кнопка вперед (якщо не вийшли за max_date)
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    next_date = date(next_year, next_month, 1)
    
    if next_date <= max_date.replace(day=1):
        nav_buttons.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=CalendarCB(action=nav_action, year=next_year, month=next_month).pack()
            )
        )
    else:
        nav_buttons.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
    
    if len(nav_buttons) == 2:
        keyboard.append(nav_buttons)

    if nearest_action:
        keyboard.append([
            InlineKeyboardButton(
                text="🔥 Найближчий вільний",
                callback_data=CalendarCB(action=nearest_action).pack(),
            )
        ])

    # Кнопка назад у меню
    from app.callbacks import MainMenuCB
    keyboard.append([
        InlineKeyboardButton(
            text="◀️ До меню",
            callback_data=MainMenuCB(action="start").pack()
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

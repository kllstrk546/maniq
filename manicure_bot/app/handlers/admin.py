from __future__ import annotations

from datetime import date, datetime, timedelta

from aiogram import F, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.callbacks import AdminCB, MainMenuCB, SlotAdminCB
from app.database import (
    DayNotFoundError,
    SlotAlreadyExistsError,
    SlotHasBookingError,
    SlotNotFoundError,
    repo_bookings,
    repo_days,
    repo_slots,
)
from app.fsm import AdminContentStates
from app.keyboards import (
    get_admin_days_keyboard,
    get_admin_menu_keyboard,
    get_admin_slots_keyboard,
)
from app.loader import dp
from app.services import (
    get_portfolio_url,
    get_prices_text,
    publish_or_update_day,
    render_day_schedule,
    set_portfolio_url,
    set_prices_text,
)
from config import ADMIN_ID


def _is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def _menu_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ Назад до адмін-панелі",
                    callback_data=AdminCB(action="back").pack(),
                )
            ]
        ]
    )


def _slot_hhmm(value: object) -> str:
    text = str(value or "")
    return text[:5] if text else "--:--"


def _display_name(booking: dict) -> str:
    name = str(booking.get("client_name") or "").strip()
    if name:
        return name
    return f"User {booking.get('user_id', '-')}"


async def _admin_summary_text(today: date) -> str:
    bookings_today = await repo_bookings.get_active_bookings_by_date(today)
    free_today = await repo_slots.get_free_slots_by_date(today)

    nearest_text = "немає"
    if bookings_today:
        nearest = bookings_today[0]
        nearest_text = f"{_slot_hhmm(nearest.get('slot_time'))} — {_display_name(nearest)}"

    return (
        "⚙️ Адмін-панель\n\n"
        f"Сьогодні: {today.strftime('%d.%m.%Y')}\n"
        f"Записів: {len(bookings_today)}\n"
        f"Вільних слотів: {len(free_today)}\n"
        f"Найближчий запис: {nearest_text}\n\n"
        "Швидкі дії:"
    )


async def _today_bookings_text(today: date) -> str:
    bookings = await repo_bookings.get_active_bookings_by_date(today)
    header = f"👥 Записи на сьогодні ({today.strftime('%d.%m.%Y')})"
    if not bookings:
        return header + "\n\nАктивних записів немає."

    lines = [header, ""]
    for idx, booking in enumerate(bookings, start=1):
        lines.append(
            f"{idx}. {_slot_hhmm(booking.get('slot_time'))} — {_display_name(booking)}"
        )
    return "\n".join(lines)


def _day_choice_keyboard(action: str, days_ahead: int = 14) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    start = date.today()
    for i in range(days_ahead):
        d = start + timedelta(days=i)
        rows.append(
            [
                InlineKeyboardButton(
                    text=d.strftime("%d.%m.%Y"),
                    callback_data=AdminCB(action=action, date=d.isoformat()).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=AdminCB(action="back").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _slot_time_choice_keyboard(target_date: date) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    hours = list(range(9, 21))
    chunk = 3
    for i in range(0, len(hours), chunk):
        row_hours = hours[i : i + chunk]
        row: list[InlineKeyboardButton] = []
        for h in row_hours:
            hhmm = f"{h:02d}:00"
            hhmm_token = hhmm.replace(":", "")
            row.append(
                InlineKeyboardButton(
                    text=hhmm,
                    callback_data=SlotAdminCB(action="add", date=target_date.isoformat(), time=hhmm_token).pack(),
                )
            )
        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton(
                text="◀️ Назад до слотів",
                callback_data=AdminCB(action="slots").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _delete_slot_keyboard(target_date: date) -> InlineKeyboardMarkup:
    slots = await repo_slots.get_all_slots_by_date(target_date)
    rows: list[list[InlineKeyboardButton]] = []

    for slot in slots:
        time_text = str(slot["slot_time"])[:5]
        time_token = time_text.replace(":", "")
        busy = bool(slot.get("booking_id"))
        prefix = "🔒" if busy else "🗑"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix} {time_text}",
                    callback_data=SlotAdminCB(
                        action="delete",
                        date=target_date.isoformat(),
                        time=time_token,
                        slot_id=int(slot["id"]),
                    ).pack(),
                )
            ]
        )

    if not rows:
        rows.append([InlineKeyboardButton(text="Слотів немає", callback_data="ignore")])

    rows.append(
        [
            InlineKeyboardButton(
                text="◀️ Назад до слотів",
                callback_data=AdminCB(action="slots").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _ensure_day(target_date: date) -> dict:
    day = await repo_days.get_day_by_date(target_date)
    if day:
        return day
    day_id = await repo_days.create_day(target_date, is_working=True)
    created = await repo_days.get_day(day_id)
    return created if created else {"id": day_id, "work_date": target_date.isoformat(), "is_working": True}


async def _safe_edit(
    query: types.CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    parse_mode: str | None = None,
) -> None:
    try:
        await query.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@dp.callback_query(MainMenuCB.filter(F.action == "admin"))
async def cb_admin_entry(
    query: types.CallbackQuery,
    callback_data: MainMenuCB,
    state: FSMContext,
) -> None:
    if not _is_admin(query.from_user.id):
        await query.answer("Недостатньо прав", show_alert=True)
        return
    await state.clear()

    await _safe_edit(
        query,
        await _admin_summary_text(date.today()),
        get_admin_menu_keyboard(),
    )
    await query.answer()


@dp.callback_query(AdminCB.filter())
async def cb_admin_actions(
    query: types.CallbackQuery,
    callback_data: AdminCB,
    state: FSMContext,
) -> None:
    if not _is_admin(query.from_user.id):
        await query.answer("Недостатньо прав", show_alert=True)
        return

    action = callback_data.action

    if action == "back":
        await state.clear()
        await _safe_edit(query, await _admin_summary_text(date.today()), get_admin_menu_keyboard())
        await query.answer()
        return

    if action == "days":
        await _safe_edit(query, "📅 Керування робочими днями", get_admin_days_keyboard())
        await query.answer()
        return

    if action == "slots":
        await _safe_edit(query, "🕐 Керування слотами", get_admin_slots_keyboard())
        await query.answer()
        return

    if action == "view_schedule":
        if not callback_data.date:
            await _safe_edit(query, "📊 Оберіть дату для перегляду розкладу", _day_choice_keyboard("view_schedule"))
            await query.answer()
            return

        target_date = date.fromisoformat(callback_data.date)
        text = await render_day_schedule(target_date)
        await _safe_edit(query, text, _menu_back_keyboard(), parse_mode="HTML")
        await query.answer()
        return

    if action == "today_bookings":
        await _safe_edit(
            query,
            await _today_bookings_text(date.today()),
            _menu_back_keyboard(),
        )
        await query.answer()
        return

    if action == "edit_prices":
        current = await get_prices_text()
        await state.set_state(AdminContentStates.editing_prices)
        await _safe_edit(
            query,
            "✏️ Надішліть новий текст прайсів (підтримується HTML).\n\n"
            "Поточний текст:\n\n"
            f"{current}",
            _menu_back_keyboard(),
        )
        await query.answer()
        return

    if action == "edit_portfolio":
        current_url = await get_portfolio_url()
        await state.set_state(AdminContentStates.editing_portfolio_url)
        await _safe_edit(
            query,
            "🔗 Надішліть нове посилання на портфоліо (https://...).\n\n"
            f"Поточне посилання:\n{current_url}",
            _menu_back_keyboard(),
        )
        await query.answer()
        return

    if action == "open_day":
        if not callback_data.date:
            await _safe_edit(query, "📅 Оберіть дату для відкриття дня", _day_choice_keyboard("open_day"))
            await query.answer()
            return

        target_date = date.fromisoformat(callback_data.date)
        day = await _ensure_day(target_date)
        await repo_days.open_day(int(day["id"]))
        await _safe_edit(
            query,
            f"✅ День відкрито: {target_date.strftime('%d.%m.%Y')}",
            get_admin_days_keyboard(),
        )
        await query.answer("День відкрито")
        return

    if action in {"close_day", "close_day_select"}:
        if not callback_data.date:
            await _safe_edit(query, "📅 Оберіть дату для закриття дня", _day_choice_keyboard("close_day"))
            await query.answer()
            return

        target_date = date.fromisoformat(callback_data.date)
        day = await _ensure_day(target_date)
        await repo_days.close_day(int(day["id"]))
        await _safe_edit(
            query,
            f"🔒 День закрито: {target_date.strftime('%d.%m.%Y')}",
            get_admin_days_keyboard(),
        )
        await query.answer("День закрито")
        return

    if action == "add_slot":
        if not callback_data.date:
            await _safe_edit(query, "🕐 Оберіть дату для додавання слота", _day_choice_keyboard("add_slot"))
            await query.answer()
            return

        target_date = date.fromisoformat(callback_data.date)
        await _safe_edit(
            query,
            f"🕐 Оберіть час слота на {target_date.strftime('%d.%m.%Y')}",
            _slot_time_choice_keyboard(target_date),
        )
        await query.answer()
        return

    if action == "delete_slot":
        if not callback_data.date:
            await _safe_edit(query, "🗑 Оберіть дату для видалення слота", _day_choice_keyboard("delete_slot"))
            await query.answer()
            return

        target_date = date.fromisoformat(callback_data.date)
        keyboard = await _delete_slot_keyboard(target_date)
        await _safe_edit(
            query,
            f"🗑 Оберіть слот для видалення на {target_date.strftime('%d.%m.%Y')}\n"
            f"(🔒 слот з активним записом видалити не можна)",
            keyboard,
        )
        await query.answer()
        return

    await query.answer("Дію поки не реалізовано", show_alert=True)


@dp.callback_query(SlotAdminCB.filter())
async def cb_admin_slot_actions(query: types.CallbackQuery, callback_data: SlotAdminCB) -> None:
    if not _is_admin(query.from_user.id):
        await query.answer("Недостатньо прав", show_alert=True)
        return

    target_date = date.fromisoformat(callback_data.date)

    if callback_data.action == "add":
        if not callback_data.time:
            await query.answer("Час не обрано", show_alert=True)
            return

        try:
            day = await _ensure_day(target_date)
            slot_time = datetime.strptime(callback_data.time, "%H%M").time()
            await repo_slots.add_slot(int(day["id"]), slot_time)
            await publish_or_update_day(target_date)
            view_hhmm = slot_time.strftime("%H:%M")
            await _safe_edit(
                query,
                f"✅ Слот {view_hhmm} додано на {target_date.strftime('%d.%m.%Y')}",
                _slot_time_choice_keyboard(target_date),
            )
            await query.answer("Слот додано")
        except SlotAlreadyExistsError:
            await query.answer("Слот уже існує", show_alert=True)
        return

    if callback_data.action == "delete":
        if callback_data.slot_id is None:
            await query.answer("Слот не обрано", show_alert=True)
            return

        try:
            await repo_slots.delete_slot(int(callback_data.slot_id))
            await publish_or_update_day(target_date)
            keyboard = await _delete_slot_keyboard(target_date)
            await _safe_edit(
                query,
                f"✅ Слот видалено на {target_date.strftime('%d.%m.%Y')}",
                keyboard,
            )
            await query.answer("Слот видалено")
        except SlotHasBookingError:
            await query.answer("Неможливо видалити: є активний запис", show_alert=True)
        except SlotNotFoundError:
            await query.answer("Слот не знайдено", show_alert=True)
        return

    await query.answer("Невідома дія", show_alert=True)


@dp.message(StateFilter(AdminContentStates.editing_prices))
async def msg_admin_edit_prices(message: types.Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("Недостатньо прав")
        await state.clear()
        return

    new_text = (message.text or "").strip()
    if not new_text:
        await message.answer("Текст не має бути порожнім. Надішліть новий текст прайсів.")
        return

    await set_prices_text(new_text)
    await state.clear()
    await message.answer("✅ Прайси оновлено.")


@dp.message(StateFilter(AdminContentStates.editing_portfolio_url))
async def msg_admin_edit_portfolio_url(message: types.Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("Недостатньо прав")
        await state.clear()
        return

    new_url = (message.text or "").strip()
    if not (new_url.startswith("http://") or new_url.startswith("https://")):
        await message.answer("Введіть коректне посилання, що починається з http:// або https://")
        return

    await set_portfolio_url(new_url)
    await state.clear()
    await message.answer("✅ Посилання на портфоліо оновлено.")

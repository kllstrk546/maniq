from __future__ import annotations

from datetime import date, timedelta
from html import escape

from aiogram import F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.callbacks import CalendarCB, ConfirmCB, MainMenuCB, SlotCB
from app.database import SlotNotAvailableError, repo_slots
from app.fsm import RescheduleStates
from app.keyboards import get_slots_keyboard
from app.loader import dp
from app.services import (
    cancel_booking_for_user,
    cancel_reminder,
    generate_calendar_keyboard,
    get_active_booking_for_user,
    get_slot_brief,
    notify_admin_cancelled,
    publish_or_update_day,
    reschedule_booking_transactional,
    schedule_reminder_for_booking,
)
from config import MAP_LINK, MASTER_LINK, SALON_ADDRESS


def _safe(value: object) -> str:
    if value is None:
        return "-"
    return escape(str(value))


def _slot_hhmm(value: object) -> str:
    text = str(value or "")
    return _safe(text[:5]) if text else "-"


def _map_html() -> str:
    if not MAP_LINK:
        return "—"
    return f'<a href="{_safe(MAP_LINK)}">Відкрити карту</a>'


def _format_booking_text(booking: dict) -> str:
    return (
        "📋 <b>Ваш активний запис</b>\n\n"
        f"📅 <b>Дата:</b> {_safe(booking.get('work_date'))}\n"
        f"🕒 <b>Час:</b> {_slot_hhmm(booking.get('slot_time'))}\n"
        f"👤 <b>Ім'я:</b> {_safe(booking.get('client_name'))}\n"
        f"📞 <b>Телефон:</b> {_safe(booking.get('client_phone'))}\n"
        f"📍 <b>Адреса / орієнтир:</b> {_safe(SALON_ADDRESS)}\n"
        f"🗺 <b>Карта:</b> {_map_html()}\n"
        "⏱ <b>Тривалість:</b> уточнюється\n"
        "📌 <b>Статус:</b> Активний ✅"
    )


def _no_booking_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 Записатися",
                    callback_data=CalendarCB(action="pick").pack(),
                ),
                InlineKeyboardButton(
                    text="◀️ До меню",
                    callback_data=MainMenuCB(action="start").pack(),
                ),
            ]
        ]
    )


def _booking_actions_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="❌ Скасувати",
                callback_data=MainMenuCB(action="cancel_booking").pack(),
            ),
            InlineKeyboardButton(
                text="🔁 Перенести",
                callback_data=MainMenuCB(action="reschedule_booking").pack(),
            ),
        ]
    ]

    if MASTER_LINK:
        rows.append([InlineKeyboardButton(text="💬 Написати майстру", url=MASTER_LINK)])
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="💬 Написати майстру",
                    callback_data=MainMenuCB(action="contact_master").pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="◀️ До меню",
                callback_data=MainMenuCB(action="start").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _cancel_confirm_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Підтвердити скасування",
                    callback_data=ConfirmCB(
                        action="confirm",
                        entity="booking",
                        entity_id=booking_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Назад",
                    callback_data=ConfirmCB(
                        action="cancel",
                        entity="booking",
                        entity_id=booking_id,
                    ).pack(),
                )
            ],
        ]
    )


def _reschedule_confirm_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Підтвердити перенесення",
                    callback_data=ConfirmCB(
                        action="confirm",
                        entity="reschedule",
                        entity_id=booking_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Скасувати",
                    callback_data=ConfirmCB(
                        action="cancel",
                        entity="reschedule",
                        entity_id=booking_id,
                    ).pack(),
                )
            ],
        ]
    )


async def _render_reschedule_calendar(
    *,
    year: int,
    month: int,
) -> InlineKeyboardMarkup:
    return await generate_calendar_keyboard(
        year=year,
        month=month,
        pick_action="reschedule_pick",
        nav_action="reschedule_nav",
        nearest_action="reschedule_nearest",
    )


async def _show_reschedule_slots(
    *,
    query: types.CallbackQuery,
    state: FSMContext,
    selected_date: str,
) -> None:
    selected_date_obj = date.fromisoformat(selected_date)
    free_slots = await repo_slots.get_free_slots_by_date(selected_date_obj)
    if not free_slots:
        await state.set_state(RescheduleStates.choosing_date)
        await query.message.edit_text(
            f"📅 {selected_date}\n\n❌ На цю дату немає вільних слотів. Оберіть іншу дату:",
            reply_markup=await _render_reschedule_calendar(
                year=selected_date_obj.year,
                month=selected_date_obj.month,
            ),
        )
        return

    await state.update_data(reschedule_date=selected_date)
    await state.set_state(RescheduleStates.choosing_time)
    await query.message.edit_text(
        f"🔁 Перенесення\n\n📅 Обрана нова дата: {selected_date}\n🕒 Оберіть новий час:",
        reply_markup=get_slots_keyboard(
            date_str=selected_date,
            slots=free_slots,
            calendar_pick_action="reschedule_pick",
        ),
    )


async def _show_my_booking(query: types.CallbackQuery) -> None:
    booking = await get_active_booking_for_user(query.from_user.id)
    if not booking:
        await query.message.edit_text(
            "📋 У вас немає активного запису.",
            reply_markup=_no_booking_keyboard(),
        )
        return

    await query.message.edit_text(
        _format_booking_text(booking),
        parse_mode="HTML",
        reply_markup=_booking_actions_keyboard(),
    )


@dp.callback_query(MainMenuCB.filter(F.action == "my_booking"))
async def cb_my_booking(query: types.CallbackQuery, callback_data: MainMenuCB) -> None:
    await _show_my_booking(query)
    await query.answer()


@dp.callback_query(MainMenuCB.filter(F.action == "contact_master"))
async def cb_contact_master_not_configured(query: types.CallbackQuery, callback_data: MainMenuCB) -> None:
    await query.answer("Контакт майстра ще не налаштований", show_alert=True)


@dp.callback_query(MainMenuCB.filter(F.action == "cancel_booking"))
async def cb_cancel_booking_request(query: types.CallbackQuery, callback_data: MainMenuCB) -> None:
    booking = await get_active_booking_for_user(query.from_user.id)
    if not booking:
        await query.message.edit_text(
            "📋 У вас немає активного запису для скасування.",
            reply_markup=_no_booking_keyboard(),
        )
        await query.answer()
        return

    await query.message.edit_text(
        _format_booking_text(booking) + "\n\n<b>Підтвердити скасування?</b>",
        parse_mode="HTML",
        reply_markup=_cancel_confirm_keyboard(booking_id=booking["id"]),
    )
    await query.answer()


@dp.callback_query(ConfirmCB.filter((F.entity == "booking") & (F.action == "cancel")))
async def cb_cancel_booking_back(query: types.CallbackQuery, callback_data: ConfirmCB) -> None:
    await _show_my_booking(query)
    await query.answer()


@dp.callback_query(ConfirmCB.filter((F.entity == "booking") & (F.action == "confirm")))
async def cb_cancel_booking_confirm(query: types.CallbackQuery, callback_data: ConfirmCB) -> None:
    active = await get_active_booking_for_user(query.from_user.id)
    if not active:
        await query.message.edit_text(
            "📋 У вас немає активного запису для скасування.",
            reply_markup=_no_booking_keyboard(),
        )
        await query.answer()
        return

    if active["id"] != callback_data.entity_id:
        await query.message.edit_text(
            _format_booking_text(active) + "\n\nЦей запис відрізняється від обраного раніше. Підтвердьте ще раз.",
            parse_mode="HTML",
            reply_markup=_cancel_confirm_keyboard(booking_id=active["id"]),
        )
        await query.answer()
        return

    cancelled = await cancel_booking_for_user(
        booking_id=callback_data.entity_id,
        user_id=query.from_user.id,
    )
    if not cancelled:
        await query.message.edit_text(
            "Не вдалося скасувати запис: він уже не активний.",
            reply_markup=_no_booking_keyboard(),
        )
        await query.answer()
        return

    booking_for_notify = {**active, **cancelled}
    await cancel_reminder(callback_data.entity_id)
    await notify_admin_cancelled(
        bot=query.bot,
        booking=booking_for_notify,
        cancelled_by="by_user",
        telegram_user=query.from_user,
    )
    await publish_or_update_day(cancelled["work_date"])

    await query.message.edit_text(
        "✅ Запис скасовано.\n\n"
        f"📅 {cancelled['work_date']}\n"
        f"🕒 {cancelled['slot_time'][:5]}",
        reply_markup=_no_booking_keyboard(),
    )
    await query.answer("Запис скасовано")


@dp.callback_query(MainMenuCB.filter(F.action == "reschedule_booking"))
async def cb_reschedule_start(
    query: types.CallbackQuery,
    callback_data: MainMenuCB,
    state: FSMContext,
) -> None:
    booking = await get_active_booking_for_user(query.from_user.id)
    if not booking:
        await query.message.edit_text(
            "📋 У вас немає активного запису для перенесення.",
            reply_markup=_no_booking_keyboard(),
        )
        await query.answer()
        return

    await state.clear()
    await state.set_state(RescheduleStates.choosing_date)
    await state.update_data(
        reschedule_booking_id=int(booking["id"]),
        reschedule_old_slot_id=int(booking["time_slot_id"]),
        reschedule_old_date=str(booking["work_date"]),
        reschedule_old_time=str(booking["slot_time"])[:5],
    )

    today = date.today()
    await query.message.edit_text(
        _format_booking_text(booking) + "\n\n🔁 <b>Перенесення</b>\nОберіть нову дату:",
        parse_mode="HTML",
        reply_markup=await _render_reschedule_calendar(year=today.year, month=today.month),
    )
    await query.answer()


@dp.callback_query(
    CalendarCB.filter(F.action == "reschedule_pick"),
    StateFilter(RescheduleStates.choosing_date),
)
async def cb_reschedule_pick_date(
    query: types.CallbackQuery,
    callback_data: CalendarCB,
    state: FSMContext,
) -> None:
    if callback_data.date is None:
        today = date.today()
        await query.message.edit_text(
            "🔁 Перенесення\n\nОберіть нову дату:",
            reply_markup=await _render_reschedule_calendar(year=today.year, month=today.month),
        )
        await query.answer()
        return

    await _show_reschedule_slots(
        query=query,
        state=state,
        selected_date=callback_data.date,
    )
    await query.answer()


@dp.callback_query(
    CalendarCB.filter(F.action == "reschedule_nav"),
    StateFilter(RescheduleStates.choosing_date),
)
async def cb_reschedule_nav(
    query: types.CallbackQuery,
    callback_data: CalendarCB,
    state: FSMContext,
) -> None:
    await query.message.edit_text(
        "🔁 Перенесення\n\nОберіть нову дату:",
        reply_markup=await _render_reschedule_calendar(
            year=int(callback_data.year),
            month=int(callback_data.month),
        ),
    )
    await query.answer()


@dp.callback_query(
    CalendarCB.filter(F.action == "reschedule_nearest"),
    StateFilter(RescheduleStates.choosing_date),
)
async def cb_reschedule_nearest(
    query: types.CallbackQuery,
    callback_data: CalendarCB,
    state: FSMContext,
) -> None:
    start = date.today()
    end = start + timedelta(days=30)
    nearest_date = await repo_slots.get_nearest_free_date(start, end)
    if nearest_date is None:
        await query.message.edit_text(
            "На найближчий місяць вільних слотів немає.",
            reply_markup=await _render_reschedule_calendar(year=start.year, month=start.month),
        )
        await query.answer()
        return

    await _show_reschedule_slots(
        query=query,
        state=state,
        selected_date=nearest_date.isoformat(),
    )
    await query.answer()


@dp.callback_query(
    SlotCB.filter(F.action == "book"),
    StateFilter(RescheduleStates.choosing_time),
)
async def cb_reschedule_pick_time(
    query: types.CallbackQuery,
    callback_data: SlotCB,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    old_slot_id = int(data["reschedule_old_slot_id"])
    new_slot_id = int(callback_data.slot_id)
    if new_slot_id == old_slot_id:
        await query.answer("Це ваш поточний слот", show_alert=True)
        return

    slot = await get_slot_brief(new_slot_id)
    if not slot or not slot["is_available"]:
        await query.answer("Слот уже зайнятий", show_alert=True)
        return

    await state.update_data(
        reschedule_new_slot_id=new_slot_id,
        reschedule_new_date=str(callback_data.date),
        reschedule_new_time=str(callback_data.time),
    )
    await state.set_state(RescheduleStates.confirming)

    old_date = str(data["reschedule_old_date"])
    old_time = str(data["reschedule_old_time"])
    new_time = str(callback_data.time)
    if len(new_time) == 4 and new_time.isdigit():
        new_time = f"{new_time[:2]}:{new_time[2:]}"

    await query.message.edit_text(
        (
            "<b>Підтвердження перенесення</b>\n\n"
            f"<b>Було:</b> {old_date} о {old_time}\n"
            f"<b>Стане:</b> {callback_data.date} о {new_time}\n\n"
            "Підтвердити перенесення?"
        ),
        parse_mode="HTML",
        reply_markup=_reschedule_confirm_keyboard(booking_id=int(data["reschedule_booking_id"])),
    )
    await query.answer()


@dp.callback_query(
    ConfirmCB.filter((F.entity == "reschedule") & (F.action == "cancel")),
    StateFilter(RescheduleStates.confirming),
)
async def cb_reschedule_cancel_confirm(
    query: types.CallbackQuery,
    callback_data: ConfirmCB,
    state: FSMContext,
) -> None:
    await state.clear()
    await _show_my_booking(query)
    await query.answer()


@dp.callback_query(
    ConfirmCB.filter((F.entity == "reschedule") & (F.action == "confirm")),
    StateFilter(RescheduleStates.confirming),
)
async def cb_reschedule_confirm(
    query: types.CallbackQuery,
    callback_data: ConfirmCB,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    booking_id = int(data.get("reschedule_booking_id", 0))
    new_slot_id = int(data.get("reschedule_new_slot_id", 0))
    if booking_id <= 0 or new_slot_id <= 0:
        await state.clear()
        await query.message.edit_text(
            "Сесія перенесення застаріла. Спробуйте ще раз.",
            reply_markup=_no_booking_keyboard(),
        )
        await query.answer()
        return

    active = await get_active_booking_for_user(query.from_user.id)
    if not active or int(active["id"]) != booking_id or callback_data.entity_id != booking_id:
        await state.clear()
        await query.message.edit_text(
            "Цей запис вже неактуальний. Відкрийте актуальний запис ще раз.",
            reply_markup=_no_booking_keyboard(),
        )
        await query.answer()
        return

    try:
        moved = await reschedule_booking_transactional(
            booking_id=booking_id,
            user_id=query.from_user.id,
            new_time_slot_id=new_slot_id,
        )
    except SlotNotAvailableError:
        await state.set_state(RescheduleStates.choosing_date)
        today = date.today()
        await query.message.edit_text(
            "Обраний слот вже недоступний. Оберіть іншу дату:",
            reply_markup=await _render_reschedule_calendar(year=today.year, month=today.month),
        )
        await query.answer()
        return

    if not moved:
        await state.clear()
        await query.message.edit_text(
            "Не вдалося перенести запис: він уже не активний.",
            reply_markup=_no_booking_keyboard(),
        )
        await query.answer()
        return

    await cancel_reminder(booking_id)
    updated_booking = await get_active_booking_for_user(query.from_user.id)
    if updated_booking:
        await schedule_reminder_for_booking(updated_booking)

    old_date = str(moved["old_work_date"])
    new_date = str(moved["work_date"])
    await publish_or_update_day(old_date)
    if new_date != old_date:
        await publish_or_update_day(new_date)

    await state.clear()
    if updated_booking:
        await query.message.edit_text(
            (
                "✅ <b>Запис успішно перенесено</b>\n\n"
                f"<b>Було:</b> {old_date} о {_slot_hhmm(moved['old_slot_time'])}\n"
                f"<b>Стане:</b> {new_date} о {_slot_hhmm(moved['slot_time'])}\n\n"
                + _format_booking_text(updated_booking)
            ),
            parse_mode="HTML",
            reply_markup=_booking_actions_keyboard(),
        )
    else:
        await query.message.edit_text(
            "✅ Запис перенесено.",
            reply_markup=_no_booking_keyboard(),
        )
    await query.answer("Запис перенесено")

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import aiosqlite
from aiogram import F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.callbacks import CalendarCB, MainMenuCB, SlotCB
from app.database import BookingAlreadyExistsError, SlotNotAvailableError, repo_slots
from app.fsm.booking_states import BookingStates
from app.keyboards import get_slots_keyboard, get_subscription_keyboard
from app.loader import dp
from app.services import (
    bind_ui_message_id,
    schedule_reminder_for_booking,
    create_booking_transactional,
    generate_calendar_keyboard,
    get_active_booking_for_user,
    get_slot_brief,
    is_subscribed,
    notify_admin_new_booking,
    publish_or_update_day,
    show_or_edit,
    user_has_active_booking,
)

PHONE_RE = re.compile(r"^\+?[0-9\-\s()]{7,20}$")


def _time_to_token(value: str) -> str:
    return value.replace(":", "")


def _token_to_time(value: str) -> str:
    if ":" in value:
        return value
    if len(value) == 4 and value.isdigit():
        return f"{value[:2]}:{value[2:]}"
    return value


def _confirm_keyboard(slot_id: int, date_str: str, time_str: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Підтвердити",
                    callback_data=SlotCB(
                        action="confirm",
                        date=date_str,
                        time=_time_to_token(time_str),
                        slot_id=slot_id,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="❌ Скасувати",
                    callback_data=SlotCB(
                        action="cancel",
                        date=date_str,
                        time=_time_to_token(time_str),
                        slot_id=slot_id,
                    ).pack(),
                ),
            ]
        ]
    )


def _after_booking_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="ℹ️ Перед візитом",
                    callback_data=MainMenuCB(action="before_visit").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 В меню",
                    callback_data=MainMenuCB(action="start").pack(),
                )
            ],
        ]
    )


def _active_booking_text(booking: dict) -> str:
    return (
        "❌ У вас вже є активний запис.\n\n"
        f"📅 Дата: {booking['work_date']}\n"
        f"🕒 Час: {booking['slot_time'][:5]}"
    )


async def _show_slots_for_date(
    *,
    state: FSMContext,
    bot,
    chat_id: int,
    selected_date: str,
) -> bool:
    selected_date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()
    free_slots = await repo_slots.get_free_slots_by_date(selected_date_obj)

    if not free_slots:
        await state.set_state(BookingStates.choosing_date)
        await show_or_edit(
            state=state,
            bot=bot,
            chat_id=chat_id,
            text=f"📅 {selected_date}\n\n❌ Немає вільних слотів. Оберіть іншу дату:",
            reply_markup=await generate_calendar_keyboard(selected_date_obj.year, selected_date_obj.month),
        )
        return False

    await state.update_data(selected_date=selected_date)
    await state.set_state(BookingStates.choosing_time)
    await show_or_edit(
        state=state,
        bot=bot,
        chat_id=chat_id,
        text=f"📅 Обрана дата: {selected_date}\n🕒 Оберіть час:",
        reply_markup=get_slots_keyboard(date_str=selected_date, slots=free_slots),
    )
    return True


@dp.callback_query(CalendarCB.filter(F.action == "pick"))
async def cb_booking_calendar_or_date(
    query: types.CallbackQuery,
    callback_data: CalendarCB,
    state: FSMContext,
) -> None:
    await bind_ui_message_id(state, query.message.message_id if query.message else None)
    chat_id = query.message.chat.id if query.message else query.from_user.id

    if not await is_subscribed(query.bot, query.from_user.id):
        await show_or_edit(
            state=state,
            bot=query.bot,
            chat_id=chat_id,
            text="❌ Щоб записатися, потрібно підписатися на канал!",
            reply_markup=get_subscription_keyboard(),
        )
        await query.answer()
        return

    if callback_data.date is None:
        active = await get_active_booking_for_user(query.from_user.id)
        if active:
            await show_or_edit(
                state=state,
                bot=query.bot,
                chat_id=chat_id,
                text=_active_booking_text(active),
            )
            await query.answer()
            return

        today = date.today()
        keyboard = await generate_calendar_keyboard(today.year, today.month)
        current_ui_message_id = query.message.message_id if query.message else None
        await state.clear()
        await state.set_state(BookingStates.choosing_date)
        await bind_ui_message_id(state, current_ui_message_id)
        await show_or_edit(
            state=state,
            bot=query.bot,
            chat_id=chat_id,
            text="📅 Оберіть дату для запису:",
            reply_markup=keyboard,
        )
        await query.answer()
        return

    await _show_slots_for_date(
        state=state,
        bot=query.bot,
        chat_id=chat_id,
        selected_date=callback_data.date,
    )
    await query.answer()


@dp.callback_query(CalendarCB.filter(F.action == "nav"))
async def cb_booking_calendar_nav(
    query: types.CallbackQuery,
    callback_data: CalendarCB,
    state: FSMContext,
) -> None:
    await bind_ui_message_id(state, query.message.message_id if query.message else None)
    chat_id = query.message.chat.id if query.message else query.from_user.id

    if not await is_subscribed(query.bot, query.from_user.id):
        await show_or_edit(
            state=state,
            bot=query.bot,
            chat_id=chat_id,
            text="❌ Щоб записатися, потрібно підписатися на канал!",
            reply_markup=get_subscription_keyboard(),
        )
        await query.answer()
        return

    keyboard = await generate_calendar_keyboard(callback_data.year, callback_data.month)
    await show_or_edit(
        state=state,
        bot=query.bot,
        chat_id=chat_id,
        text="📅 Оберіть дату для запису:",
        reply_markup=keyboard,
    )
    await query.answer()


@dp.callback_query(CalendarCB.filter(F.action == "nearest"))
async def cb_booking_nearest_free(
    query: types.CallbackQuery,
    callback_data: CalendarCB,
    state: FSMContext,
) -> None:
    await bind_ui_message_id(state, query.message.message_id if query.message else None)
    chat_id = query.message.chat.id if query.message else query.from_user.id

    if not await is_subscribed(query.bot, query.from_user.id):
        await show_or_edit(
            state=state,
            bot=query.bot,
            chat_id=chat_id,
            text="❌ Щоб записатися, потрібно підписатися на канал!",
            reply_markup=get_subscription_keyboard(),
        )
        await query.answer()
        return

    active = await get_active_booking_for_user(query.from_user.id)
    if active:
        await show_or_edit(
            state=state,
            bot=query.bot,
            chat_id=chat_id,
            text=_active_booking_text(active),
        )
        await query.answer()
        return

    today = date.today()
    nearest_date = await repo_slots.get_nearest_free_date(today, today + timedelta(days=30))
    if nearest_date is None:
        await state.set_state(BookingStates.choosing_date)
        await show_or_edit(
            state=state,
            bot=query.bot,
            chat_id=chat_id,
            text="На найближчий місяць вільних слотів немає.",
            reply_markup=await generate_calendar_keyboard(today.year, today.month),
        )
        await query.answer()
        return

    await _show_slots_for_date(
        state=state,
        bot=query.bot,
        chat_id=chat_id,
        selected_date=nearest_date.isoformat(),
    )
    await query.answer()


@dp.callback_query(SlotCB.filter(F.action == "book"), StateFilter(BookingStates.choosing_time))
async def cb_booking_pick_time(
    query: types.CallbackQuery,
    callback_data: SlotCB,
    state: FSMContext,
) -> None:
    await bind_ui_message_id(state, query.message.message_id if query.message else None)
    chat_id = query.message.chat.id if query.message else query.from_user.id

    slot = await get_slot_brief(int(callback_data.slot_id))
    if not slot or not slot["is_available"]:
        await query.answer("Слот уже зайнятий", show_alert=True)
        return

    time_display = _token_to_time(callback_data.time)
    await state.update_data(
        slot_id=int(callback_data.slot_id),
        slot_time=time_display,
        selected_date=callback_data.date,
    )
    await state.set_state(BookingStates.entering_name)
    await show_or_edit(
        state=state,
        bot=query.bot,
        chat_id=chat_id,
        text=f"📅 {callback_data.date}  🕒 {time_display}\n\nВведіть ваше ім'я:",
    )
    await query.answer()


@dp.message(StateFilter(BookingStates.entering_name))
async def msg_booking_name(message: types.Message, state: FSMContext) -> None:
    chat_id = message.chat.id
    name = (message.text or "").strip()
    if len(name) < 2 or len(name) > 64:
        await show_or_edit(
            state=state,
            bot=message.bot,
            chat_id=chat_id,
            text="Введіть коректне ім'я (2-64 символи).",
        )
        return

    await state.update_data(client_name=name)
    await state.set_state(BookingStates.entering_phone)
    await show_or_edit(
        state=state,
        bot=message.bot,
        chat_id=chat_id,
        text="Введіть номер телефону:",
    )


@dp.message(StateFilter(BookingStates.entering_phone))
async def msg_booking_phone(message: types.Message, state: FSMContext) -> None:
    chat_id = message.chat.id
    phone = (message.text or "").strip()
    if not PHONE_RE.match(phone):
        await show_or_edit(
            state=state,
            bot=message.bot,
            chat_id=chat_id,
            text="Введіть коректний номер телефону, наприклад +380501234567.",
        )
        return

    data = await state.get_data()
    slot_id = int(data["slot_id"])
    date_str = data["selected_date"]
    time_str = data["slot_time"]
    name = data["client_name"]

    await state.update_data(client_phone=phone)
    await state.set_state(BookingStates.confirming)

    await show_or_edit(
        state=state,
        bot=message.bot,
        chat_id=chat_id,
        text=(
            "<b>Підтвердження запису</b>\n\n"
            f"<b>Дата:</b> {date_str}\n"
            f"<b>Час:</b> {time_str}\n"
            f"<b>Ім'я:</b> {name}\n"
            f"<b>Телефон:</b> {phone}\n\n"
            "Підтвердити запис?"
        ),
        parse_mode="HTML",
        reply_markup=_confirm_keyboard(slot_id=slot_id, date_str=date_str, time_str=time_str),
    )


@dp.callback_query(SlotCB.filter(F.action == "cancel"), StateFilter(BookingStates.confirming))
async def cb_booking_cancel_confirm(query: types.CallbackQuery, state: FSMContext) -> None:
    await bind_ui_message_id(state, query.message.message_id if query.message else None)
    chat_id = query.message.chat.id if query.message else query.from_user.id

    await show_or_edit(
        state=state,
        bot=query.bot,
        chat_id=chat_id,
        text="Запис скасовано.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="◀️ До меню",
                        callback_data=MainMenuCB(action="start").pack(),
                    )
                ]
            ]
        ),
    )
    await state.clear()
    await query.answer()


@dp.callback_query(SlotCB.filter(F.action == "confirm"), StateFilter(BookingStates.confirming))
async def cb_booking_confirm(
    query: types.CallbackQuery,
    callback_data: SlotCB,
    state: FSMContext,
) -> None:
    user_id = query.from_user.id
    await bind_ui_message_id(state, query.message.message_id if query.message else None)
    chat_id = query.message.chat.id if query.message else query.from_user.id

    if await user_has_active_booking(user_id):
        active = await get_active_booking_for_user(user_id)
        if active:
            await show_or_edit(
                state=state,
                bot=query.bot,
                chat_id=chat_id,
                text=_active_booking_text(active),
            )
        else:
            await show_or_edit(
                state=state,
                bot=query.bot,
                chat_id=chat_id,
                text="❌ У вас вже є активний запис.",
            )
        await state.clear()
        await query.answer()
        return

    data = await state.get_data()
    slot_id = int(data["slot_id"])

    if slot_id != int(callback_data.slot_id):
        await show_or_edit(
            state=state,
            bot=query.bot,
            chat_id=chat_id,
            text="Сесія підтвердження застаріла. Почніть запис знову.",
        )
        await state.clear()
        await query.answer()
        return

    try:
        created_booking_id = await create_booking_transactional(
            user_id=user_id,
            time_slot_id=slot_id,
            client_name=data["client_name"],
            client_phone=data["client_phone"],
        )
    except BookingAlreadyExistsError:
        active = await get_active_booking_for_user(user_id)
        if active:
            await show_or_edit(
                state=state,
                bot=query.bot,
                chat_id=chat_id,
                text=_active_booking_text(active),
            )
        else:
            await show_or_edit(
                state=state,
                bot=query.bot,
                chat_id=chat_id,
                text="❌ У вас вже є активний запис.",
            )
        await state.clear()
        await query.answer()
        return
    except (SlotNotAvailableError, aiosqlite.IntegrityError):
        await show_or_edit(
            state=state,
            bot=query.bot,
            chat_id=chat_id,
            text="Слот уже зайнятий",
        )
        await state.clear()
        await query.answer()
        return

    booking_for_notify = await get_active_booking_for_user(user_id)
    if booking_for_notify is None:
        booking_for_notify = {
            "id": created_booking_id,
            "user_id": user_id,
            "client_name": data["client_name"],
            "client_phone": data["client_phone"],
            "work_date": data["selected_date"],
            "slot_time": data["slot_time"],
        }
    await schedule_reminder_for_booking(booking_for_notify)
    await notify_admin_new_booking(
        bot=query.bot,
        booking=booking_for_notify,
        telegram_user=query.from_user,
    )
    await publish_or_update_day(data["selected_date"])

    await show_or_edit(
        state=state,
        bot=query.bot,
        chat_id=chat_id,
        text=(
            "✅ Запис підтверджено!\n\n"
            f"📅 Дата: {data['selected_date']}\n"
            f"🕒 Час: {data['slot_time']}\n"
            f"👤 Ім'я: {data['client_name']}\n"
            f"📞 Телефон: {data['client_phone']}"
        ),
        reply_markup=_after_booking_confirm_keyboard(),
    )
    await state.clear()
    await query.answer()

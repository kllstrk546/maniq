from datetime import date

from aiogram import F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from app.callbacks import MainMenuCB
from app.keyboards import get_main_menu_keyboard, get_subscription_keyboard
from app.loader import dp
from app.services import generate_calendar_keyboard, is_subscribed
from config import ADMIN_ID, CHANNEL_ID


def _channel_id_as_int(value: str) -> int | None:
    raw = (value or "").strip()
    if raw.lstrip("-").isdigit():
        return int(raw)
    return None


TARGET_CHANNEL_ID = _channel_id_as_int(CHANNEL_ID)


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "👋 Ласкаво просимо до бота для запису на манікюр!\n\nОберіть дію:",
        reply_markup=get_main_menu_keyboard(user_id=message.from_user.id, admin_id=ADMIN_ID),
    )


@dp.callback_query(MainMenuCB.filter(F.action == "start"))
async def cb_main_menu(
    query: types.CallbackQuery,
    callback_data: MainMenuCB,
    state: FSMContext,
) -> None:
    await state.clear()
    await query.message.edit_text(
        "👋 Головне меню:\n\nОберіть дію:",
        reply_markup=get_main_menu_keyboard(user_id=query.from_user.id, admin_id=ADMIN_ID),
    )
    await query.answer()


@dp.callback_query(MainMenuCB.filter(F.action == "check_subscription"))
async def cb_check_subscription(query: types.CallbackQuery, callback_data: MainMenuCB) -> None:
    if await is_subscribed(query.bot, query.from_user.id):
        today = date.today()
        await query.message.edit_text(
            "✅ Підписку підтверджено.\n\n📅 Оберіть дату для запису:",
            reply_markup=await generate_calendar_keyboard(year=today.year, month=today.month),
        )
    else:
        await query.message.edit_text(
            "❌ Ви не підписані на канал.\n\nЩоб записатися, потрібно підписатися.",
            reply_markup=get_subscription_keyboard(),
        )
    await query.answer()


@dp.chat_join_request()
async def chat_join_request_approve(event: types.ChatJoinRequest) -> None:
    """Автосхвалення заявки на вступ до каналу підписки."""
    if TARGET_CHANNEL_ID is not None and event.chat.id != TARGET_CHANNEL_ID:
        return
    await event.approve()


@dp.callback_query(F.data == "ignore")
async def cb_ignore(query: types.CallbackQuery) -> None:
    """Тихо обробляє технічні кнопки календаря."""
    await query.answer()

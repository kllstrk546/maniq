from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup

UI_MESSAGE_ID_KEY = "ui_message_id"


def _can_fallback_to_new_message(exc: Exception) -> bool:
    if not isinstance(exc, TelegramBadRequest):
        return True

    text = str(exc).lower()
    fallback_markers = (
        "message to edit not found",
        "message can't be edited",
        "chat not found",
        "message id is invalid",
        "message identifier is not specified",
        "have no rights to send a message",
    )
    return any(marker in text for marker in fallback_markers)


async def bind_ui_message_id(state: FSMContext, message_id: int | None) -> None:
    if message_id is None:
        return
    await state.update_data(**{UI_MESSAGE_ID_KEY: int(message_id)})


async def show_or_edit(
    *,
    state: FSMContext,
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> int:
    data = await state.get_data()
    ui_message_id = data.get(UI_MESSAGE_ID_KEY)

    if ui_message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=int(ui_message_id),
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
            return int(ui_message_id)
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return int(ui_message_id)
            elif not _can_fallback_to_new_message(exc):
                raise
            else:
                ui_message_id = None
        except TelegramAPIError:
            ui_message_id = None

    sent = await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )
    await bind_ui_message_id(state, sent.message_id)
    return int(sent.message_id)

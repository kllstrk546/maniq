from aiogram import F, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.callbacks import MainMenuCB
from app.keyboards import get_prices_keyboard
from app.loader import dp
from app.services import get_portfolio_url, get_prices_text


def _render_prices_menu(prices_text: str) -> str:
    lines = [line.strip() for line in prices_text.splitlines() if line.strip()]
    if not lines:
        lines = ["Прайс тимчасово порожній"]

    divider = "<code>──────────────</code>"
    body = "\n".join([divider, *[f"• {line}" for line in lines], divider])
    return "<b>💅 Прайс</b>\n\n" + body


def _before_visit_text() -> str:
    return (
        "<b>ℹ️ Перед візитом</b>\n\n"
        "<b>Як підготуватися:</b>\n"
        "• За 24 години не використовуйте олію/крем на нігтях.\n"
        "• Зніміть попереднє покриття заздалегідь (якщо потрібно).\n"
        "• Приходьте без запізнення.\n\n"
        "<b>Політика скасування:</b>\n"
        "• Скасування або перенесення не пізніше ніж за 12 годин.\n\n"
        "<b>Запізнення:</b>\n"
        "• Понад 10 хвилин — слот може бути втрачений."
    )


def _before_visit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏠 В меню",
                    callback_data=MainMenuCB(action="start").pack(),
                )
            ]
        ]
    )


@dp.callback_query(MainMenuCB.filter(F.action == "prices"))
async def cb_prices(query: types.CallbackQuery, callback_data: MainMenuCB) -> None:
    prices_text = await get_prices_text()
    await query.message.edit_text(
        _render_prices_menu(prices_text),
        parse_mode="HTML",
        reply_markup=get_prices_keyboard(),
    )
    await query.answer()


@dp.callback_query(MainMenuCB.filter(F.action == "portfolio"))
async def cb_portfolio(query: types.CallbackQuery, callback_data: MainMenuCB) -> None:
    portfolio_url = await get_portfolio_url()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Дивитися портфоліо",
                    url=portfolio_url,
                )
            ],
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
    await query.message.edit_text(
        "Портфоліо майстра:",
        reply_markup=keyboard,
    )
    await query.answer()


@dp.callback_query(MainMenuCB.filter(F.action == "before_visit"))
async def cb_before_visit(query: types.CallbackQuery, callback_data: MainMenuCB) -> None:
    await query.message.edit_text(
        _before_visit_text(),
        parse_mode="HTML",
        reply_markup=_before_visit_keyboard(),
    )
    await query.answer()

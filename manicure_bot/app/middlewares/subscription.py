"""Middleware перевірки підписки на канал."""
from typing import Callable, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from app.services.subscription_service import is_subscribed
from app.keyboards.subscription import get_subscription_keyboard


class SubscriptionMiddleware(BaseMiddleware):
    """Middleware для перевірки підписки перед записом."""
    
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any]
    ) -> Any:
        """Перевіряє підписку для повідомлень."""
        # Пропускаємо команду /start та інші базові команди
        if event.text and event.text.startswith(('/start', '/help', '/menu')):
            return await handler(event, data)
        
        # Перевіряємо підписку
        bot = data.get("bot")
        if bot and not await is_subscribed(bot, event.from_user.id):
            await event.answer(
                "❌ Щоб записатися, потрібно підписатися на канал!",
                reply_markup=get_subscription_keyboard()
            )
            return None
        
        return await handler(event, data)


class CallbackSubscriptionMiddleware(BaseMiddleware):
    """Middleware для перевірки підписки на callback-запити (запис)."""
    
    # Список callback-дій, які вимагають підписки
    BOOKING_ACTIONS = {'pick', 'book', 'confirm', 'nearest'}
    
    async def __call__(
        self,
        handler: Callable[[CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: dict[str, Any]
    ) -> Any:
        """Перевіряє підписку для callback-ів, що ведуть до запису."""
        callback_data = data.get("callback_data")
        
        # Якщо це callback, пов'язаний із записом - перевіряємо підписку
        if callback_data and hasattr(callback_data, 'action'):
            if callback_data.action in self.BOOKING_ACTIONS:
                bot = data.get("bot")
                if bot and not await is_subscribed(bot, event.from_user.id):
                    await event.message.edit_text(
                        "❌ Щоб записатися, потрібно підписатися на канал!",
                        reply_markup=get_subscription_keyboard()
                    )
                    await event.answer()
                    return None
        
        return await handler(event, data)

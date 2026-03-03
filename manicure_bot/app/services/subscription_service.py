"""Subscription checks for booking access."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatIdUnion

from config import CHANNEL_ID

logger = logging.getLogger(__name__)


def _normalize_chat_id(raw_chat_id: str) -> ChatIdUnion:
    """Accept -100..., @username, username or t.me/username and normalize for Bot API."""
    value = (raw_chat_id or "").strip()
    if not value:
        return value

    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        if parsed.netloc in {"t.me", "www.t.me", "telegram.me", "www.telegram.me"}:
            value = parsed.path.strip("/").split("/")[0]

    if value.startswith("@"):
        return value

    if value.lstrip("-").isdigit():
        return int(value)

    return f"@{value}"


def _is_active_member(member: object) -> bool:
    status = getattr(member, "status", None)
    if status in {
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
    }:
        return True
    if status == ChatMemberStatus.RESTRICTED:
        return bool(getattr(member, "is_member", False))
    return False


async def is_subscribed(bot: Bot, user_id: int) -> bool:
    """Return True when user is channel member or membership cannot be checked by API."""
    chat_id = _normalize_chat_id(CHANNEL_ID)
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return _is_active_member(member)
    except TelegramBadRequest as exc:
        # If Telegram hides member list from this bot, strict verification is impossible.
        # Fail-open to avoid blocking legitimate users and log exact reason.
        if "member list is inaccessible" in str(exc).lower():
            logger.warning(
                "Subscription check is unavailable for chat %r: %s. "
                "Allowing user %s without strict check.",
                chat_id,
                exc,
                user_id,
            )
            return True

        logger.warning(
            "Subscription check failed for chat %r, user %s: %s",
            chat_id,
            user_id,
            exc,
        )
        return False
    except Exception:
        logger.exception(
            "Unexpected error during subscription check for chat %r, user %s",
            chat_id,
            user_id,
        )
        return False

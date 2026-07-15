from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType, ParseMode
from aiogram.types import (
    CallbackQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
    TelegramObject,
    User,
)

logger = logging.getLogger(__name__)

ACCESS_DENIED_TEXT = (
    "<b>Доступ закрыт</b>\n\n"
    "Velvet Archive работает в частном режиме и доступен только владельцу."
)
ACCESS_DENIED_CALLBACK_TEXT = "Доступ к Velvet Archive закрыт."


def normalize_username(value: str) -> str:
    return value.strip().lstrip("@").casefold()


@dataclass(frozen=True, slots=True)
class AccessPolicy:
    allowed_user_ids: frozenset[int]
    allowed_usernames: frozenset[str]

    def allows_user(self, user: User | None) -> bool:
        if user is None:
            return False

        if user.id in self.allowed_user_ids:
            return True

        username = normalize_username(user.username or "")
        return bool(username and username in self.allowed_usernames)


def get_caller_user(message: Message) -> User | None:
    return message.from_user or message.guest_bot_caller_user


def message_requires_owner_access(message: Message) -> bool:
    """Protect commands and private/guest interactions without blocking topic ingestion."""
    if message.guest_query_id:
        return True

    if message.chat.type == ChatType.PRIVATE:
        return True

    text = message.text or message.caption or ""
    return text.lstrip().startswith("/")


async def answer_access_denied(message: Message) -> None:
    if message.guest_query_id:
        result_id = hashlib.sha256(
            f"access-denied:{message.guest_query_id}".encode("utf-8")
        ).hexdigest()[:32]
        await message.answer_guest_query(
            InlineQueryResultArticle(
                id=result_id,
                title="Velvet Archive",
                input_message_content=InputTextMessageContent(
                    message_text=ACCESS_DENIED_TEXT,
                    parse_mode=ParseMode.HTML,
                ),
            )
        )
        return

    await message.answer(ACCESS_DENIED_TEXT)


class OwnerAccessMiddleware(BaseMiddleware):
    def __init__(self, policy: AccessPolicy) -> None:
        self.policy = policy

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, CallbackQuery):
            allowed = self.policy.allows_user(event.from_user)
            logger.info(
                "Callback access check: caller_id=%s username=%s allowed=%s",
                event.from_user.id,
                event.from_user.username,
                allowed,
            )
            if allowed:
                return await handler(event, data)

            await event.answer(
                ACCESS_DENIED_CALLBACK_TEXT,
                show_alert=True,
            )
            return None

        if not isinstance(event, Message):
            return await handler(event, data)

        if not message_requires_owner_access(event):
            return await handler(event, data)

        caller = get_caller_user(event)
        allowed = self.policy.allows_user(caller)

        if event.guest_query_id:
            logger.info(
                "Guest access check: caller_id=%s username=%s allowed=%s",
                caller.id if caller else None,
                caller.username if caller else None,
                allowed,
            )

        if allowed:
            return await handler(event, data)

        await answer_access_denied(event)
        return None

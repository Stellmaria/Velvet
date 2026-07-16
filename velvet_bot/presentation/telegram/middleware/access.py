from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType, ParseMode
from aiogram.types import (
    CallbackQuery,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
    TelegramObject,
    User,
)

from velvet_bot.core.access import (
    AccessPolicy,
    CHARACTER_EDITOR_COMMANDS,
    CHARACTER_EDITOR_USER_IDS,
    PROMPT_REPLY_MARKER,
    command_name,
    is_owner_mention_text,
    is_public_command_text,
)

logger = logging.getLogger(__name__)

PUBLIC_CALLBACK_PREFIX = "pub:"
CHARACTER_EDITOR_CALLBACK_PREFIXES = ("adir:", "astory:", "arc:")

ACCESS_DENIED_TEXT = (
    "<b>Доступ закрыт</b>\n\n"
    "Служебные команды Velvet Archive доступны только владельцу. "
    "Открытый архив персонажей: <code>/archive</code>."
)
ACCESS_DENIED_CALLBACK_TEXT = "Эта служебная кнопка доступна только владельцу."


def is_public_callback(callback: CallbackQuery) -> bool:
    return bool(callback.data and callback.data.startswith(PUBLIC_CALLBACK_PREFIX))


def is_character_editor_user(user: User | None) -> bool:
    return bool(user and user.id in CHARACTER_EDITOR_USER_IDS)


def is_character_editor_callback(callback: CallbackQuery) -> bool:
    return bool(
        is_character_editor_user(callback.from_user)
        and callback.data
        and callback.data.startswith(CHARACTER_EDITOR_CALLBACK_PREFIXES)
    )


def get_caller_user(message: Message) -> User | None:
    return message.from_user or message.guest_bot_caller_user


def is_character_editor_message(message: Message) -> bool:
    caller = get_caller_user(message)
    if not is_character_editor_user(caller):
        return False

    text = message.text or message.caption or ""
    if command_name(text) in CHARACTER_EDITOR_COMMANDS:
        return True

    reply = message.reply_to_message
    if reply is None:
        return False
    reply_text = reply.text or reply.caption or ""
    return PROMPT_REPLY_MARKER in reply_text


def message_requires_owner_access(
    message: Message,
    bot_username: str = "",
) -> bool:
    if message.guest_query_id:
        return True
    if message.chat.type == ChatType.PRIVATE:
        return True

    text = message.text or message.caption or ""
    stripped = text.lstrip()
    if stripped.startswith("/"):
        return True
    return is_owner_mention_text(stripped, bot_username)


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
            if is_public_callback(event) or is_character_editor_callback(event):
                return await handler(event, data)

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

        if isinstance(event, InlineQuery):
            allowed = self.policy.allows_user(event.from_user)
            logger.info(
                "Inline access check: caller_id=%s username=%s allowed=%s",
                event.from_user.id,
                event.from_user.username,
                allowed,
            )
            if allowed:
                return await handler(event, data)
            await event.answer(
                [
                    InlineQueryResultArticle(
                        id="access-denied",
                        title="Доступ закрыт",
                        description="Inline-режим доступен только владельцу.",
                        input_message_content=InputTextMessageContent(
                            message_text=ACCESS_DENIED_TEXT,
                            parse_mode=ParseMode.HTML,
                        ),
                    )
                ],
                cache_time=1,
                is_personal=True,
            )
            return None

        if not isinstance(event, Message):
            return await handler(event, data)

        text = event.text or event.caption or ""
        if is_public_command_text(text) or is_character_editor_message(event):
            return await handler(event, data)

        if not message_requires_owner_access(
            event,
            str(data.get("bot_username", "")),
        ):
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


__all__ = (
    "ACCESS_DENIED_CALLBACK_TEXT",
    "ACCESS_DENIED_TEXT",
    "CHARACTER_EDITOR_CALLBACK_PREFIXES",
    "OwnerAccessMiddleware",
    "PUBLIC_CALLBACK_PREFIX",
    "answer_access_denied",
    "get_caller_user",
    "is_character_editor_callback",
    "is_character_editor_message",
    "is_character_editor_user",
    "is_public_callback",
    "message_requires_owner_access",
)

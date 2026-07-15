from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
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

logger = logging.getLogger(__name__)

PUBLIC_COMMANDS = frozenset({"start", "archive", "gallery", "menu"})
PUBLIC_CALLBACK_PREFIX = "pub:"

CHARACTER_EDITOR_USER_IDS = frozenset({8179531132})
CHARACTER_EDITOR_COMMANDS = frozenset({"characters", "prompt", "setprompt"})
CHARACTER_EDITOR_CALLBACK_PREFIXES = ("adir:", "astory:", "arc:")
_PROMPT_REPLY_MARKER = "PROMPT_MEDIA:"

ACCESS_DENIED_TEXT = (
    "<b>Доступ закрыт</b>\n\n"
    "Служебные команды Velvet Archive доступны только владельцу. "
    "Открытый архив персонажей: <code>/archive</code>."
)
ACCESS_DENIED_CALLBACK_TEXT = "Эта служебная кнопка доступна только владельцу."


def normalize_username(value: str) -> str:
    return value.strip().lstrip("@").casefold()


def command_name(text: str) -> str | None:
    cleaned = text.strip()
    if not cleaned.startswith("/"):
        return None
    command_token = cleaned.split(maxsplit=1)[0][1:]
    return command_token.split("@", maxsplit=1)[0].casefold()


def is_public_command_text(text: str) -> bool:
    """Return True only for commands intentionally exposed to every subscriber."""
    command = command_name(text)
    return bool(command and command in PUBLIC_COMMANDS)


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


def is_character_editor_message(message: Message) -> bool:
    caller = get_caller_user(message)
    if not is_character_editor_user(caller):
        return False

    text = message.text or message.caption or ""
    command = command_name(text)
    if command in CHARACTER_EDITOR_COMMANDS:
        return True

    reply = message.reply_to_message
    if reply is None:
        return False
    reply_text = reply.text or reply.caption or ""
    return _PROMPT_REPLY_MARKER in reply_text


def is_owner_mention_text(text: str, bot_username: str) -> bool:
    """Recognize owner-only archive and reference actions in ordinary chats."""
    expected = normalize_username(bot_username)
    cleaned = " ".join(text.split())
    if not expected or not cleaned:
        return False

    escaped = re.escape(expected)
    action = r"(?:save|refadd|refdel|refs?)"
    return bool(
        re.fullmatch(
            rf"(?:"
            rf"@{escaped}\s+/?{action}\s+.+|"
            rf"/?{action}\s+@{escaped}\s+.+|"
            rf"/?{action}\s+.+\s+@{escaped}"
            rf")",
            cleaned,
            re.IGNORECASE,
        )
    )


# Backward-compatible alias for existing tests and imports.
def is_save_mention_text(text: str, bot_username: str) -> bool:
    return is_owner_mention_text(text, bot_username)


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


def message_requires_owner_access(
    message: Message,
    bot_username: str = "",
) -> bool:
    """Protect commands and private/guest interactions without blocking topic ingestion."""
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

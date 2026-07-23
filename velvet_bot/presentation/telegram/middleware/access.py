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
    CHARACTER_TAG_REPLY_MARKER,
    MODERATOR_CALLBACK_PREFIXES,
    MODERATOR_COMMANDS,
    MODERATOR_TAG_COMMANDS,
    PROMPT_REPLY_MARKER,
    PUBLIC_CALLBACK_PREFIX,
    command_name,
    is_moderator_callback_data,
    is_owner_mention_text,
    is_public_callback_data,
    is_public_command_text,
    is_workspace_member_callback_data,
    is_workspace_member_command_text,
    is_workspace_member_fsm_state_name,
)
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.service import WorkspaceAccessError

logger = logging.getLogger(__name__)

# Compatibility alias. The role is deliberately narrower than an admin.
CHARACTER_EDITOR_CALLBACK_PREFIXES = MODERATOR_CALLBACK_PREFIXES

ACCESS_DENIED_TEXT = (
    "<b>Доступ закрыт</b>\n\n"
    "В открытом доступе находятся публичные архивы персонажей. "
    "Создание личного архива появляется после выдачи доступа Стэл."
)
ACCESS_DENIED_CALLBACK_TEXT = (
    "Эта служебная кнопка недоступна. Откройте публичные архивы через /start."
)


def is_public_callback(callback: CallbackQuery) -> bool:
    return is_public_callback_data(callback.data)


def is_moderator_user(
    user: User | None,
    moderator_user_ids: frozenset[int] = frozenset(),
) -> bool:
    return bool(user and user.id in moderator_user_ids)


def is_moderator_callback(
    callback: CallbackQuery,
    moderator_user_ids: frozenset[int] = frozenset(),
) -> bool:
    return bool(
        is_moderator_user(callback.from_user, moderator_user_ids)
        and is_moderator_callback_data(callback.data)
    )


def get_caller_user(message: Message) -> User | None:
    return message.from_user or message.guest_bot_caller_user


def is_moderator_message(
    message: Message,
    moderator_user_ids: frozenset[int] = frozenset(),
) -> bool:
    caller = get_caller_user(message)
    if not is_moderator_user(caller, moderator_user_ids):
        return False

    text = message.text or message.caption or ""
    if command_name(text) in (MODERATOR_COMMANDS | MODERATOR_TAG_COMMANDS):
        return True

    reply = message.reply_to_message
    if reply is None:
        return False
    reply_text = reply.text or reply.caption or ""
    return bool(
        PROMPT_REPLY_MARKER in reply_text
        or CHARACTER_TAG_REPLY_MARKER in reply_text
    )


# Compatibility aliases used by existing imports and tests.
is_character_editor_user = is_moderator_user
is_character_editor_callback = is_moderator_callback
is_character_editor_message = is_moderator_message


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


async def _workspace_state_name(data: dict[str, Any]) -> str | None:
    state = data.get("state")
    get_state = getattr(state, "get_state", None)
    if get_state is None:
        return None
    current = await get_state()
    return str(current) if current else None


async def _workspace_form_is_active(data: dict[str, Any]) -> bool:
    current = await _workspace_state_name(data)
    return is_workspace_member_fsm_state_name(current)


async def _workspace_creation_name_form_is_active(data: dict[str, Any]) -> bool:
    """Allow the name submitted after a validated create-workspace callback.

    At this point the caller cannot have an active personal workspace yet. Requiring
    one would intercept the very message that creates it and return the generic access
    denial shown in Telegram. The callback that starts this state already verifies the
    creation grant, and the service verifies it again before writing the workspace.
    """

    current = await _workspace_state_name(data)
    return bool(current and current.endswith(":waiting_workspace_name"))


async def _has_active_personal_workspace(
    data: dict[str, Any],
    user: User | None,
) -> bool:
    workspace_service = data.get("workspace_service")
    if workspace_service is None or user is None:
        return False
    try:
        workspace = await workspace_service.resolve_active_workspace(
            user_id=int(user.id),
            global_owner=False,
        )
    except WorkspaceAccessError:
        return False
    return int(workspace.id) != DEFAULT_WORKSPACE_ID


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
    """Apply global-owner, moderator, public and guarded workspace access."""

    def __init__(self, policy: AccessPolicy) -> None:
        self.policy = policy

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, CallbackQuery):
            if is_public_callback(event) or is_moderator_callback(
                event,
                self.policy.moderator_user_ids,
            ):
                return await handler(event, data)
            if is_workspace_member_callback_data(
                event.data
            ) and await _has_active_personal_workspace(
                data,
                event.from_user,
            ):
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
            await event.answer(ACCESS_DENIED_CALLBACK_TEXT, show_alert=True)
            return None

        if isinstance(event, InlineQuery):
            if await _has_active_personal_workspace(data, event.from_user):
                return await handler(event, data)
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
        if is_public_command_text(text) or is_moderator_message(
            event,
            self.policy.moderator_user_ids,
        ):
            return await handler(event, data)

        caller = get_caller_user(event)
        # Workspace callbacks start signed FSM sessions. The initial workspace-name
        # form is the one exception that must continue before a workspace exists.
        # All other forms still require an active personal workspace, and their target
        # handlers recheck membership, role and module policy before writing data.
        if await _workspace_form_is_active(data):
            if await _workspace_creation_name_form_is_active(
                data
            ) or await _has_active_personal_workspace(data, caller):
                return await handler(event, data)

        personal_route = is_workspace_member_command_text(text) or (
            event.chat.type == ChatType.PRIVATE and command_name(text) is None
        )
        if personal_route and await _has_active_personal_workspace(data, caller):
            return await handler(event, data)

        if not message_requires_owner_access(
            event,
            str(data.get("bot_username", "")),
        ):
            return await handler(event, data)

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
    "is_moderator_callback",
    "is_moderator_message",
    "is_moderator_user",
    "is_public_callback",
    "message_requires_owner_access",
)

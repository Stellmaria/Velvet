from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, InlineQuery, Message, TelegramObject, User

from velvet_bot.domains.user_registry import (
    TelegramUserIdentity,
    TelegramUserRepository,
)

logger = logging.getLogger(__name__)


class UserActivityMiddleware(BaseMiddleware):
    """Record privacy-minimal user activity without blocking Telegram handling."""

    def __init__(self, repository: TelegramUserRepository) -> None:
        self._repository = repository

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            observation = await _observation(event, data)
            if observation is not None:
                identity, fields = observation
                await self._repository.observe(identity, **fields)
        except asyncio.CancelledError:
            raise
        except Exception:  # p2-approved-boundary: user-observability-must-not-block-bot
            logger.exception("Could not persist Telegram user activity")
        return await handler(event, data)


async def _observation(
    event: TelegramObject,
    data: dict[str, Any],
) -> tuple[TelegramUserIdentity, dict[str, Any]] | None:
    user = _event_user(event)
    if user is None:
        return None

    event_type = "update"
    chat_id: int | None = None
    chat_type: str | None = None
    command: str | None = None
    callback_action: str | None = None
    module_key: str | None = None
    workspace_id: int | None = None

    if isinstance(event, Message):
        chat_id = int(event.chat.id)
        chat_type = str(event.chat.type.value)
        command = _command_name(event.text or event.caption or "")
        event_type = "command" if command else "message"
        module_key = _module_from_command(command)
        if module_key is None:
            module_key = await _module_from_state(data)
    elif isinstance(event, CallbackQuery):
        event_type = "callback"
        callback_action, module_key, workspace_id = _callback_metadata(event.data)
        if event.message is not None:
            chat = getattr(event.message, "chat", None)
            if chat is not None:
                chat_id = int(chat.id)
                chat_type = str(chat.type.value)
    elif isinstance(event, InlineQuery):
        event_type = "inline"
        module_key = "inline"

    return (
        TelegramUserIdentity(
            user_id=int(user.id),
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
            is_bot=bool(user.is_bot),
            is_premium=getattr(user, "is_premium", None),
        ),
        {
            "event_type": event_type,
            "chat_id": chat_id,
            "chat_type": chat_type,
            "module_key": module_key,
            "command_name": command,
            "callback_action": callback_action,
            "workspace_id": workspace_id,
        },
    )


def _event_user(event: TelegramObject) -> User | None:
    if isinstance(event, Message):
        return event.from_user or event.guest_bot_caller_user
    if isinstance(event, (CallbackQuery, InlineQuery)):
        return event.from_user
    return None


def _command_name(text: str) -> str | None:
    stripped = str(text or "").lstrip()
    if not stripped.startswith("/"):
        return None
    token = stripped.split(maxsplit=1)[0][1:]
    return token.split("@", 1)[0].casefold()[:64] or None


def _module_from_command(command: str | None) -> str | None:
    if not command:
        return None
    if command in {"auf", "refs", "velvet_grant", "velvet_user", "velvet_users"}:
        return "auf"
    if command in {"start", "help"}:
        return "start"
    if command.startswith("workspace") or command in {"my", "home"}:
        return "workspace"
    if command.startswith("public"):
        return "public_archive"
    if command.startswith("rp") or command.startswith("roleplay"):
        return "roleplay"
    return command[:48]


async def _module_from_state(data: dict[str, Any]) -> str | None:
    state = data.get("state")
    getter = getattr(state, "get_state", None)
    if getter is None:
        return None
    current = await getter()
    if not current:
        return None
    prefix = str(current).split(":", 1)[0].casefold()
    if "auf" in prefix or "meow" in prefix:
        return "auf"
    if "workspace" in prefix:
        return "workspace"
    if "roleplay" in prefix or prefix.startswith("rp"):
        return "roleplay"
    return prefix[:48] or None


def _callback_metadata(data: str | None) -> tuple[str | None, str | None, int | None]:
    raw = str(data or "").strip()
    if not raw:
        return None, None, None
    parts = raw.split(":")
    prefix = parts[0].casefold()
    action = parts[1][:96] if len(parts) > 1 else prefix[:96]
    module = {
        "auf": "auf",
        "meow": "auf",
        "workspace": "workspace",
        "ws": "workspace",
        "public": "public_archive",
        "rp": "roleplay",
        "supervisor": "supervisor",
    }.get(prefix, prefix[:48] or None)
    workspace_id: int | None = None
    if prefix in {"auf", "meow", "workspace", "ws"} and len(parts) > 2:
        try:
            candidate = int(parts[2])
        except (TypeError, ValueError):
            candidate = 0
        workspace_id = candidate if candidate > 0 else None
    return action or None, module, workspace_id


__all__ = ("UserActivityMiddleware",)

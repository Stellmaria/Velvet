from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BotCommand, BotCommandScopeChat

from velvet_bot.core.access import CHARACTER_EDITOR_USER_IDS
from velvet_bot.core.config import Settings

logger = logging.getLogger(__name__)


def build_public_commands() -> tuple[BotCommand, ...]:
    return (
        BotCommand(command="start", description="Открыть меню"),
        BotCommand(command="archive", description="Архив персонажей"),
    )


def build_editor_commands() -> tuple[BotCommand, ...]:
    return (
        BotCommand(command="start", description="Открыть меню"),
        BotCommand(command="menu", description="Центр управления"),
        BotCommand(command="archive", description="Архив персонажей"),
    )


def build_admin_commands() -> tuple[BotCommand, ...]:
    # Служебные slash-команды сохранены в обработчиках как аварийный резерв,
    # но обычное меню Telegram ведёт владельца в единый кнопочный центр.
    return (
        BotCommand(command="start", description="Открыть центр управления"),
        BotCommand(command="menu", description="Центр управления"),
        BotCommand(command="archive", description="Архив персонажей"),
    )


async def _set_scoped_commands(
    bot: Bot,
    *,
    commands: tuple[BotCommand, ...],
    chat_ids: set[int] | frozenset[int],
    role_name: str,
) -> None:
    for chat_id in sorted(chat_ids):
        try:
            await bot.set_my_commands(
                list(commands),
                scope=BotCommandScopeChat(chat_id=chat_id),
            )
        except TelegramBadRequest as error:
            logger.warning(
                "Could not set %s command menu for %s: %s",
                role_name,
                chat_id,
                error,
            )


async def install_command_menus(bot: Bot, settings: Settings) -> None:
    """Install compact command menus; all normal management lives in buttons."""
    await bot.set_my_commands(list(build_public_commands()))
    await _set_scoped_commands(
        bot,
        commands=build_editor_commands(),
        chat_ids=CHARACTER_EDITOR_USER_IDS,
        role_name="editor",
    )
    await _set_scoped_commands(
        bot,
        commands=build_admin_commands(),
        chat_ids=settings.allowed_user_ids,
        role_name="owner",
    )


__all__ = (
    "build_admin_commands",
    "build_editor_commands",
    "build_public_commands",
    "install_command_menus",
)

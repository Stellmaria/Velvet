from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeChat, CallbackQuery, Message

logger = logging.getLogger(__name__)

_ROLE_RANK = {
    "viewer": 10,
    "reviewer": 20,
    "editor": 30,
    "admin": 40,
    "owner": 50,
}


def workspace_commands(role: str) -> tuple[BotCommand, ...]:
    commands = [
        BotCommand(command="start", description="Открыть пространство"),
        BotCommand(command="archive", description="Архив этого пространства"),
        BotCommand(command="refs", description="Референсы персонажа"),
        BotCommand(command="compare_ref", description="Сравнить с референсом"),
    ]
    if _ROLE_RANK.get(role, 0) >= _ROLE_RANK["editor"]:
        commands.extend(
            [
                BotCommand(command="save", description="Сохранить материалы персонажу"),
                BotCommand(command="savecancel", description="Завершить пакетное сохранение"),
                BotCommand(command="refadd", description="Добавить референс"),
                BotCommand(command="refdel", description="Удалить референс"),
                BotCommand(command="watermark", description="Подготовить watermark"),
            ]
        )
    return tuple(commands)


async def set_workspace_chat_commands(bot: Bot, chat_id: int, role: str) -> None:
    try:
        await bot.set_my_commands(
            list(workspace_commands(role)),
            scope=BotCommandScopeChat(chat_id=int(chat_id)),
        )
    except TelegramAPIError as error:
        logger.warning(
            "Could not install workspace command menu for chat %s: %s",
            chat_id,
            error,
        )


async def install_workspace_scoped_commands(
    callback: CallbackQuery,
    *,
    role: str,
) -> None:
    chat_id = (
        callback.message.chat.id
        if isinstance(callback.message, Message)
        else callback.from_user.id
    )
    await set_workspace_chat_commands(callback.bot, chat_id, role)


__all__ = (
    "install_workspace_scoped_commands",
    "set_workspace_chat_commands",
    "workspace_commands",
)

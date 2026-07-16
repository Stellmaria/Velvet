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
        *build_public_commands(),
        BotCommand(command="characters", description="Категории и персонажи"),
        BotCommand(command="prompt", description="Привязать вариант промта"),
    )


def build_admin_commands() -> tuple[BotCommand, ...]:
    return (
        *build_public_commands(),
        BotCommand(command="system", description="Состояние бота и фоновых процессов"),
        BotCommand(command="supervisor", description="Перезапуск, Git, логи и Codex"),
        BotCommand(command="logs", description="Последние строки журнала бота"),
        BotCommand(command="restart", description="Безопасно перезапустить бота"),
        BotCommand(command="update", description="Обновить main, проверить и перезапустить"),
        BotCommand(command="rollback", description="Откатить последнее развёртывание"),
        BotCommand(command="codex", description="Поставить задачу Codex"),
        BotCommand(command="codex_status", description="Проверить задачу Codex"),
        BotCommand(command="version", description="Версия приложения и схемы"),
        BotCommand(command="analytics", description="Аналитический центр"),
        BotCommand(command="backup", description="Резервные копии PostgreSQL"),
        BotCommand(command="quality", description="Контроль качества и дубли"),
        BotCommand(command="publish", description="Проверка и очередь публикаций"),
        BotCommand(command="checkpost", description="Проверить пост ответом"),
        BotCommand(command="create", description="Создать персонажа и назначить тему"),
        BotCommand(command="topic", description="Назначить тему персонажу"),
        BotCommand(command="characters", description="Категории и персонажи"),
        BotCommand(command="category", description="Назначить пол или состав"),
        BotCommand(command="universe", description="Назначить вселенную"),
        BotCommand(command="story", description="Назначить историю"),
        BotCommand(command="stories", description="Список историй вселенной"),
        BotCommand(command="storyadd", description="Добавить новую историю"),
        BotCommand(command="prompt", description="Привязать пост с промтом"),
        BotCommand(command="character", description="Профиль персонажа"),
        BotCommand(command="save", description="Сохранить фото или видео"),
        BotCommand(command="refadd", description="Добавить референсы персонажа"),
        BotCommand(command="refdone", description="Завершить загрузку референсов"),
        BotCommand(command="refs", description="Показать референсы персонажа"),
        BotCommand(command="refdel", description="Удалить референс по номеру"),
        BotCommand(command="aliasadd", description="Добавить алиас персонажа"),
        BotCommand(command="aliases", description="Показать алиасы персонажа"),
        BotCommand(command="aliasdel", description="Удалить алиас персонажа"),
        BotCommand(command="aliasreindex", description="Пересобрать связи хэштегов"),
        BotCommand(command="channelstats", description="Общая статистика канала"),
        BotCommand(command="promptstats", description="Статистика структуры промтов"),
        BotCommand(command="tagstats", description="Статистика хэштегов"),
        BotCommand(command="characterstats", description="Частота персонажей в канале"),
        BotCommand(command="importchannel", description="Импорт экспорта канала"),
        BotCommand(command="importdiscussion", description="Импорт обсуждения"),
        BotCommand(command="trackdiscussion", description="Подключить чат обсуждений"),
        BotCommand(command="discussionstats", description="Статистика обсуждения"),
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
    """Install public, editor and owner command menus in one place."""
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

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from velvet_bot.application.arthur_librarian import ArthurLibrarianApplication
from velvet_bot.core.config.arthur import ArthurSettings
from velvet_bot.database import Database
from velvet_bot.domains.telegram_storage.librarian_models import (
    StorageLibrarianSettings,
)
from velvet_bot.presentation.telegram.arthur_librarian import (
    build_arthur_dispatcher,
)
from velvet_bot.presentation.telegram.arthur_report_publisher import (
    ArthurReportPublisher,
)

logger = logging.getLogger(__name__)

_COMMANDS = (
    BotCommand(command="start", description="Назначение Arthur"),
    BotCommand(command="status", description="Сервисы и модель"),
    BotCommand(command="archive", description="Запуск/остановка архива"),
    BotCommand(command="analyze", description="Анализ Storage ID"),
    BotCommand(command="result", description="Сохранённый результат"),
    BotCommand(command="ask", description="Вопрос по индексу"),
    BotCommand(command="digest", description="Сводка анализов"),
    BotCommand(command="queue", description="Storage queue"),
    BotCommand(command="download", description="Скачать Storage ID"),
    BotCommand(command="help", description="Команды и ограничения"),
)


async def _heartbeat(path: Path) -> None:
    while True:
        path.write_text("ok\n", encoding="utf-8")
        await asyncio.sleep(20)


async def run_arthur() -> None:
    settings = ArthurSettings.from_env()
    librarian_settings = StorageLibrarianSettings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    database = Database(settings.database_url)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    heartbeat_task: asyncio.Task[None] | None = None
    application: ArthurLibrarianApplication | None = None
    try:
        await database.initialize()
        identity = await bot.get_me()
        report_publisher = ArthurReportPublisher(
            bot,
            chat_id=settings.report_chat_id,
            thread_id=settings.report_thread_id,
        )
        application = ArthurLibrarianApplication(
            settings=settings,
            librarian_settings=librarian_settings,
            database=database,
            report_publisher=report_publisher,
        )
        dispatcher = build_arthur_dispatcher(
            settings=settings,
            application=application,
        )
        await bot.set_my_commands(list(_COMMANDS))
        heartbeat_task = asyncio.create_task(
            _heartbeat(settings.heartbeat_path),
            name="arthur-heartbeat",
        )
        logger.info(
            "Arthur started bot=@%s owners=%s usernames=%s",
            identity.username or "",
            sorted(settings.allowed_user_ids),
            sorted(settings.allowed_usernames),
        )
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        if application is not None:
            await application.shutdown()
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task
        settings.heartbeat_path.unlink(missing_ok=True)
        await bot.session.close()
        await database.close()


def main() -> None:
    asyncio.run(run_arthur())


__all__ = ("main", "run_arthur")

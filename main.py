import asyncio
import logging
from contextlib import suppress

from aiogram import Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BotCommand, BotCommandScopeChat

from velvet_bot.access import AccessPolicy, OwnerAccessMiddleware
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.config import load_settings
from velvet_bot.database import Database
from velvet_bot.handlers import router
from velvet_bot.protected_bot import ProtectedMediaBot
from velvet_bot.public_notifications import run_public_notification_worker
from velvet_bot.public_ui import PUBLIC_DOWNLOAD_USER_ID
from velvet_bot.reference_uploads import ReferenceUploadSessions

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = load_settings()
    database = Database(settings.database_url)
    await database.initialize()

    bot = ProtectedMediaBot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        unprotected_private_user_ids={PUBLIC_DOWNLOAD_USER_ID},
    )
    audit_logger = TelegramAuditLogger(bot, settings.log_chat_id)
    reference_uploads = ReferenceUploadSessions()
    notification_task: asyncio.Task[None] | None = None

    try:
        bot_info = await bot.get_me()
        bot_username = bot_info.username or ""

        if bot_info.supports_guest_queries:
            logger.info("Guest Mode enabled for @%s", bot_username)
        else:
            logger.warning(
                "Guest Mode is not enabled for @%s in BotFather",
                bot_username,
            )

        access_policy = AccessPolicy(
            allowed_user_ids=settings.allowed_user_ids,
            allowed_usernames=settings.allowed_usernames,
        )
        access_middleware = OwnerAccessMiddleware(access_policy)

        dispatcher = Dispatcher()
        dispatcher.workflow_data.update(
            {
                "database": database,
                "bot_username": bot_username,
                "audit_logger": audit_logger,
                "reference_uploads": reference_uploads,
                "access_policy": access_policy,
            }
        )
        dispatcher.message.outer_middleware(access_middleware)
        dispatcher.guest_message.outer_middleware(access_middleware)
        dispatcher.callback_query.outer_middleware(access_middleware)
        dispatcher.inline_query.outer_middleware(access_middleware)
        dispatcher.include_router(router)

        logger.info(
            "Owner access enabled for ids=%s usernames=%s",
            sorted(settings.allowed_user_ids),
            sorted(settings.allowed_usernames),
        )

        public_commands = [
            BotCommand(command="start", description="Открыть меню"),
            BotCommand(command="archive", description="Архив персонажей"),
        ]
        admin_commands = [
            *public_commands,
            BotCommand(command="create", description="Создать персонажа и назначить тему"),
            BotCommand(command="topic", description="Назначить тему персонажу"),
            BotCommand(command="characters", description="Категории и персонажи"),
            BotCommand(command="category", description="Назначить пол или состав"),
            BotCommand(command="universe", description="Назначить вселенную"),
            BotCommand(command="prompt", description="Привязать пост с промтом"),
            BotCommand(command="character", description="Профиль персонажа"),
            BotCommand(command="save", description="Сохранить фото или видео"),
            BotCommand(command="refadd", description="Добавить референсы персонажа"),
            BotCommand(command="refdone", description="Завершить загрузку референсов"),
            BotCommand(command="refs", description="Показать референсы персонажа"),
            BotCommand(command="refdel", description="Удалить референс по номеру"),
        ]
        await bot.set_my_commands(public_commands)
        for owner_id in settings.allowed_user_ids:
            try:
                await bot.set_my_commands(
                    admin_commands,
                    scope=BotCommandScopeChat(chat_id=owner_id),
                )
            except TelegramBadRequest as error:
                logger.warning(
                    "Could not set private owner command menu for %s: %s",
                    owner_id,
                    error,
                )

        allowed_updates = dispatcher.resolve_used_update_types()
        logger.info("Allowed Telegram updates: %s", ", ".join(allowed_updates))
        await audit_logger.send(
            "Velvet Archive запущен",
            level="SUCCESS",
            bot=f"@{bot_username}",
            guest_mode=bot_info.supports_guest_queries,
            allowed_updates=", ".join(allowed_updates),
            log_chat_id=settings.log_chat_id,
        )

        notification_task = asyncio.create_task(
            run_public_notification_worker(bot, database),
            name="public-archive-notifications",
        )
        await dispatcher.start_polling(
            bot,
            allowed_updates=allowed_updates,
            database=database,
            bot_username=bot_username,
            audit_logger=audit_logger,
            reference_uploads=reference_uploads,
            access_policy=access_policy,
        )
    finally:
        if notification_task is not None:
            notification_task.cancel()
            with suppress(asyncio.CancelledError):
                await notification_task
        await audit_logger.send("Velvet Archive остановлен", level="WARNING")
        await bot.session.close()
        await database.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    asyncio.run(main())

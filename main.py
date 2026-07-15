import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from velvet_bot.access import AccessPolicy, OwnerAccessMiddleware
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.config import load_settings
from velvet_bot.database import Database
from velvet_bot.handlers import router

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = load_settings()
    database = Database(settings.database_url)
    await database.initialize()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    audit_logger = TelegramAuditLogger(bot, settings.log_chat_id)

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

        dispatcher = Dispatcher(
            database=database,
            bot_username=bot_username,
            audit_logger=audit_logger,
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

        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Запустить бота"),
                BotCommand(command="create", description="Создать персонажа и назначить тему"),
                BotCommand(command="topic", description="Назначить тему персонажу"),
                BotCommand(command="characters", description="Список персонажей"),
                BotCommand(command="character", description="Профиль персонажа"),
                BotCommand(command="save", description="Сохранить фото или видео"),
            ]
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

        await dispatcher.start_polling(
            bot,
            allowed_updates=allowed_updates,
        )
    finally:
        await audit_logger.send("Velvet Archive остановлен", level="WARNING")
        await bot.session.close()
        await database.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    asyncio.run(main())

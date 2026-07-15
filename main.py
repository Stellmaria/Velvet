import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from velvet_bot.config import load_settings
from velvet_bot.database import Database
from velvet_bot.handlers import router


async def main() -> None:
    settings = load_settings()
    database = Database(settings.database_path)
    await database.initialize()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(database=database)
    dispatcher.include_router(router)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Запустить бота"),
            BotCommand(command="create", description="Создать персонажа"),
            BotCommand(command="characters", description="Список персонажей"),
            BotCommand(command="character", description="Профиль персонажа"),
        ]
    )

    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    asyncio.run(main())

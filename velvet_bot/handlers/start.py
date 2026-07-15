from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name=__name__)


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    user_name = message.from_user.first_name if message.from_user else ""
    greeting = f", {user_name}" if user_name else ""

    await message.answer(
        f"<b>Velvet Archive</b>{greeting}\n\n"
        "Бот запущен и готов к работе. "
        "Скоро здесь появится архив персонажей и команды сохранения."
    )

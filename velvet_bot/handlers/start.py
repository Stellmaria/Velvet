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
        "Создать персонажа: <code>/create Каин</code>\n"
        "Показать персонажей: <code>/characters</code>\n"
        "Открыть профиль: <code>/character Каин</code>\n\n"
        "Чтобы сохранить изображение из группы, добавьте бота в чат, "
        "ответьте на нужное изображение и отправьте "
        "<code>/save@имя_бота Каин</code>."
    )

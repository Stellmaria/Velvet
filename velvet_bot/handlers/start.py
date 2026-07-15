from html import escape

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name=__name__)


@router.message(CommandStart())
async def handle_start(message: Message, bot_username: str) -> None:
    user_name = message.from_user.first_name if message.from_user else ""
    greeting = f", {user_name}" if user_name else ""
    safe_username = escape(bot_username or "имя_бота")

    await message.answer(
        f"<b>Velvet Archive</b>{greeting}\n\n"
        "Создать персонажа: <code>/create Каин</code>\n"
        "Показать персонажей: <code>/characters</code>\n"
        "Открыть профиль: <code>/character Каин</code>\n\n"
        "Чтобы сохранить изображение из любого чата, ответьте на него и отправьте:\n"
        f"<code>@{safe_username} save Каин</code>\n"
        "или\n"
        f"<code>/save@{safe_username} Каин</code>"
    )

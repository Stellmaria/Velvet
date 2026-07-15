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
        "Создать персонажа и назначить тему:\n"
        "<code>/create Аид https://t.me/c/3951213065/1398</code>\n\n"
        "Назначить тему существующему персонажу:\n"
        "<code>/topic Аид https://t.me/c/3951213065/1398</code>\n\n"
        "Показать персонажей: <code>/characters</code>\n"
        "Открыть профиль: <code>/character Аид</code>\n\n"
        "Добавить одну или несколько фотографий-референсов:\n"
        "<code>/refadd Аид</code> → отправить фото → <code>/refdone</code>\n\n"
        "Показать референсы: <code>/refs Аид</code>\n"
        "Вызвать референсы в любом чате:\n"
        f"<code>@{safe_username} ref Аид</code>\n\n"
        "Чтобы сохранить фото или видео из любого чата, ответьте на него и отправьте:\n"
        f"<code>@{safe_username} save Аид</code>"
    )

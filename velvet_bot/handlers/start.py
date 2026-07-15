from html import escape

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from velvet_bot.access import AccessPolicy
from velvet_bot.public_ui import build_public_entry_keyboard

router = Router(name=__name__)


@router.message(CommandStart())
async def handle_start(
    message: Message,
    bot_username: str,
    access_policy: AccessPolicy,
) -> None:
    is_owner = access_policy.allows_user(message.from_user)
    if not is_owner:
        await message.answer(
            "<b>Velvet Archive</b>\n\n"
            "Открытый архив персонажей доступен подписчикам через меню ниже. "
            "Внутри можно листать материалы, ставить отметки и подписываться "
            "на обновления любимых персонажей.",
            reply_markup=build_public_entry_keyboard(),
        )
        return

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
        "Добавить референсы в личке:\n"
        "<code>/refadd Аид</code> → отправить фото или JPG/PNG/WEBP документ → "
        "<code>/refdone</code>\n\n"
        "Добавить один референс из любого чата: ответьте на фото или "
        "изображение-документ и отправьте:\n"
        f"<code>@{safe_username} refadd Аид</code>\n\n"
        "Показать все референсы: <code>/ref Аид</code>\n"
        "Показать только один: <code>/ref Аид 1</code> или "
        "<code>/ref Аид #2</code>\n"
        "Удалить один референс: <code>/refdel Аид 2</code>\n\n"
        "Открытое меню подписчиков: <code>/archive</code>\n\n"
        "Чтобы сохранить фото или видео в общий архив, ответьте на него и отправьте:\n"
        f"<code>@{safe_username} save Аид</code>",
        reply_markup=build_public_entry_keyboard(),
    )

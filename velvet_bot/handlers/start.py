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
            "Выберите категорию персонажей, затем откройте нужную карточку. "
            "Списки отсортированы по алфавиту и разбиты на страницы. "
            "Внутри можно листать материалы, ставить отметки, подписываться "
            "на обновления и открывать пост с промтом, когда он привязан.",
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
        "Категории и карточки: <code>/characters</code>\n"
        "Назначить категорию: <code>/category Аид мужской</code>\n"
        "Доступны: женский, мужской, мж, мм, жж.\n"
        "Привязать пост с промтом: "
        "<code>/prompt Аид https://t.me/channel/123</code>\n"
        "Удалить ссылку: <code>/prompt Аид off</code>\n\n"
        "Назначить тему существующему персонажу:\n"
        "<code>/topic Аид https://t.me/c/3951213065/1398</code>\n\n"
        "Добавить референсы в личке:\n"
        "<code>/refadd Аид</code> → отправить фото или JPG/PNG/WEBP документ → "
        "<code>/refdone</code>\n\n"
        "Добавить один референс из любого чата: ответьте на фото или "
        "изображение-документ и отправьте:\n"
        f"<code>@{safe_username} refadd Аид</code>\n\n"
        "Показать все референсы: <code>/ref Аид</code>\n"
        "Показать только один: <code>/ref Аид 1</code>\n"
        "Удалить один: <code>/refdel Аид 2</code>\n\n"
        "Открытое меню подписчиков: <code>/archive</code>\n\n"
        "Чтобы сохранить фото или видео, ответьте на него и отправьте:\n"
        f"<code>@{safe_username} save Аид</code>",
        reply_markup=build_public_entry_keyboard(),
    )

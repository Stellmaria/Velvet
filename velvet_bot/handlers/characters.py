from html import escape

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from velvet_bot.archive_ui import (
    build_character_archive_keyboard,
    build_character_list_keyboard,
)
from velvet_bot.database import Character, Database
from velvet_bot.topics import TopicReference, split_character_and_topic

router = Router(name=__name__)


async def _validate_topic_access(bot: Bot, topic: TopicReference) -> None:
    chat = await bot.get_chat(topic.chat_id)
    if not chat.is_forum:
        raise ValueError("Ссылка должна вести в тему группы с включёнными ветками.")

    bot_info = await bot.get_me()
    member = await bot.get_chat_member(topic.chat_id, bot_info.id)
    if member.status not in {
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
    }:
        raise ValueError(
            "Бот должен быть администратором группы, к теме которой привязывается персонаж."
        )


async def _bind_topic(
    bot: Bot,
    database: Database,
    character: Character,
    topic: TopicReference,
) -> Character:
    await _validate_topic_access(bot, topic)
    return await database.bind_character_topic(
        character.id,
        archive_chat_id=topic.chat_id,
        archive_thread_id=topic.thread_id,
        archive_topic_url=topic.url,
    )


def _topic_line(character: Character) -> str:
    if not character.archive_topic_url:
        return "Тема архива: <b>не назначена</b>"
    safe_url = escape(character.archive_topic_url, quote=True)
    return f'<a href="{safe_url}">Тема архива</a>'


@router.message(Command("create", "crete"))
async def handle_create_character(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
) -> None:
    if not command.args:
        await message.answer(
            "Укажите имя персонажа и ссылку на его тему.\n\n"
            "Пример:\n"
            "<code>/create Аид https://t.me/c/3951213065/1398</code>"
        )
        return

    try:
        character_name, topic = split_character_and_topic(command.args)
        character, created = await database.create_character(
            character_name,
            created_by=message.from_user.id if message.from_user else None,
            created_in_chat=message.chat.id,
        )
        if topic is not None:
            character = await _bind_topic(bot, database, character, topic)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    except Exception as error:
        await message.answer(
            "Не удалось проверить или привязать тему Telegram.\n"
            f"<code>{escape(str(error))}</code>"
        )
        return

    safe_name = escape(character.name)
    media_count = await database.count_character_media(character.id)

    if created:
        heading = "<b>Профиль персонажа создан</b>"
    elif topic is not None:
        heading = "<b>Профиль уже существовал, тема архива обновлена</b>"
    else:
        heading = "<b>Профиль уже существует</b>"

    await message.answer(
        f"{heading}\n\n"
        f"Имя: <b>{safe_name}</b>\n"
        f"ID: <code>{character.id}</code>\n"
        f"Фото и видео в архиве: <b>{media_count}</b>\n"
        f"{_topic_line(character)}\n\n"
        "Новые фото и видео из назначенной темы будут учитываться автоматически. "
        "Медиа, сохранённые через <code>/save</code> или Guest Mode, "
        "бот отправит в эту тему.",
        reply_markup=build_character_archive_keyboard(character, media_count),
    )


@router.message(Command("topic"))
async def handle_bind_character_topic(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
) -> None:
    if not command.args:
        await message.answer(
            "Укажите персонажа и ссылку на тему.\n\n"
            "Пример:\n"
            "<code>/topic Аид https://t.me/c/3951213065/1398</code>"
        )
        return

    try:
        character_name, topic = split_character_and_topic(command.args)
        if topic is None:
            raise ValueError("После имени укажите ссылку на тему Telegram.")

        character = await database.get_character(character_name)
        if character is None:
            await message.answer(
                "Такой персонаж не найден.\n"
                "Сначала создайте его командой <code>/create Имя</code>."
            )
            return

        character = await _bind_topic(bot, database, character, topic)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    except Exception as error:
        await message.answer(
            "Не удалось проверить или привязать тему Telegram.\n"
            f"<code>{escape(str(error))}</code>"
        )
        return

    media_count = await database.count_character_media(character.id)
    await message.answer(
        "<b>Тема архива назначена</b>\n\n"
        f"Персонаж: <b>{escape(character.name)}</b>\n"
        f"{_topic_line(character)}",
        reply_markup=build_character_archive_keyboard(character, media_count),
    )


@router.message(Command("characters"))
async def handle_list_characters(message: Message, database: Database) -> None:
    characters = await database.list_characters()
    if not characters:
        await message.answer(
            "Профилей персонажей пока нет.\n\n"
            "Создание:\n"
            "<code>/create Аид https://t.me/c/3951213065/1398</code>"
        )
        return

    lines = ["<b>Персонажи Velvet Archive</b>", ""]
    for index, character in enumerate(characters, start=1):
        topic_mark = " 📁" if character.archive_topic_url else ""
        lines.append(
            f"{index}. <b>{escape(character.name)}</b> "
            f"<code>#{character.id}</code>{topic_mark}"
        )
    lines.extend(
        [
            "",
            "📁 — назначена тема архива",
            "Нажмите кнопку персонажа, чтобы открыть его медиа.",
        ]
    )

    await message.answer(
        "\n".join(lines),
        reply_markup=build_character_list_keyboard(characters),
    )


@router.message(Command("character"))
async def handle_character(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer(
            "Укажите имя персонажа.\n\n"
            "Пример: <code>/character Аид</code>"
        )
        return

    try:
        character = await database.get_character(command.args)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return

    if character is None:
        await message.answer(
            "Такой персонаж не найден.\n\n"
            "Список: <code>/characters</code>"
        )
        return

    media_count = await database.count_character_media(character.id)
    created_at = character.created_at.astimezone().strftime(
        "%d.%m.%Y %H:%M:%S %Z"
    )
    await message.answer(
        "<b>Профиль персонажа</b>\n\n"
        f"Имя: <b>{escape(character.name)}</b>\n"
        f"ID: <code>{character.id}</code>\n"
        f"Фото и видео в архиве: <b>{media_count}</b>\n"
        f"{_topic_line(character)}\n"
        f"Создан: <code>{escape(created_at)}</code>",
        reply_markup=build_character_archive_keyboard(character, media_count),
    )

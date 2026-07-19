import logging
from functools import partial
from html import escape

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from velvet_bot.application.owner_profiles import (
    bind_character_topic,
    create_character_profile,
    load_character_profile,
)
from velvet_bot.archive_ui import (
    build_character_archive_keyboard,
    build_character_list_keyboard,
)
from velvet_bot.database import Character, Database
from velvet_bot.services.telegram_topics import validate_topic_access

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_SHARED_TOPIC_NOTE = (
    "Одна ветка может быть связана с несколькими персонажами. "
    "Новые материалы из неё сохраняются во все связанные карточки."
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
            "Укажите имя персонажа и при необходимости ссылку на его тему.\n\n"
            "Пример:\n"
            "<code>/create Аид https://t.me/c/3951213065/1398</code>"
        )
        return
    try:
        result = await create_character_profile(
            database,
            command.args,
            actor_id=message.from_user.id if message.from_user else None,
            chat_id=message.chat.id,
            validate_topic=partial(validate_topic_access, bot),
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    except Exception as error:  # p2-approved-boundary: report-character-create-failure
        logger.exception("Failed to create character profile")
        await message.answer(
            "Не удалось проверить или привязать тему Telegram.\n"
            f"<code>{escape(str(error))}</code>"
        )
        return

    profile = result.profile
    character = profile.character
    if result.created:
        heading = "<b>Профиль персонажа создан</b>"
    elif result.topic_supplied:
        heading = "<b>Профиль уже существовал, тема архива добавлена</b>"
    else:
        heading = "<b>Профиль уже существует</b>"
    topic_note = f"\n\n{_SHARED_TOPIC_NOTE}" if result.topic_supplied else ""
    await message.answer(
        f"{heading}\n\n"
        f"Имя: <b>{escape(character.name)}</b>\n"
        f"ID: <code>{character.id}</code>\n"
        f"Фото и видео в архиве: <b>{profile.media_count}</b>\n"
        f"Референсов: <b>{profile.reference_count}</b>\n"
        f"{_topic_line(character)}\n\n"
        "Новые фото и видео из назначенной темы будут учитываться автоматически."
        f"{topic_note}",
        reply_markup=build_character_archive_keyboard(character, profile.media_count),
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
        profile = await bind_character_topic(
            database,
            command.args,
            validate_topic=partial(validate_topic_access, bot),
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    except Exception as error:  # p2-approved-boundary: report-character-topic-failure
        logger.exception("Failed to bind character topic")
        await message.answer(
            "Не удалось проверить или привязать тему Telegram.\n"
            f"<code>{escape(str(error))}</code>"
        )
        return
    await message.answer(
        "<b>Тема архива добавлена</b>\n\n"
        f"Персонаж: <b>{escape(profile.character.name)}</b>\n"
        f"{_topic_line(profile.character)}\n\n"
        f"{_SHARED_TOPIC_NOTE}",
        reply_markup=build_character_archive_keyboard(
            profile.character,
            profile.media_count,
        ),
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
        profile = await load_character_profile(database, command.args)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    if profile is None:
        await message.answer("Такой персонаж не найден.\n\nСписок: <code>/characters</code>")
        return
    character = profile.character
    created_at = character.created_at.astimezone().strftime("%d.%m.%Y %H:%M:%S %Z")
    await message.answer(
        "<b>Профиль персонажа</b>\n\n"
        f"Имя: <b>{escape(character.name)}</b>\n"
        f"ID: <code>{character.id}</code>\n"
        f"Фото и видео в архиве: <b>{profile.media_count}</b>\n"
        f"Референсов: <b>{profile.reference_count}</b>\n"
        f"{_topic_line(character)}\n"
        f"Создан: <code>{escape(created_at)}</code>",
        reply_markup=build_character_archive_keyboard(character, profile.media_count),
    )

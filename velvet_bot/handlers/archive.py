from __future__ import annotations

import hashlib
import logging
import re
from html import escape

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)

from velvet_bot.database import Database
from velvet_bot.media import extract_image

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_GUEST_COMMAND_PATTERN = re.compile(
    r"^/save(?:@(?P<bot>[A-Za-z0-9_]+))?\s+(?P<name>.+)$",
    re.IGNORECASE,
)
_GUEST_MENTION_PATTERN = re.compile(
    r"^@(?P<bot>[A-Za-z0-9_]+)\s+/?save\s+(?P<name>.+)$",
    re.IGNORECASE,
)
_GUEST_PLAIN_PATTERN = re.compile(
    r"^/?save\s+(?P<name>.+)$",
    re.IGNORECASE,
)


def parse_guest_save_character(text: str, bot_username: str) -> str | None:
    """Extract a character name from a Guest Mode summon message."""
    cleaned = " ".join(text.split())
    if not cleaned:
        return None

    expected_username = bot_username.lstrip("@").casefold()

    for pattern in (
        _GUEST_COMMAND_PATTERN,
        _GUEST_MENTION_PATTERN,
        _GUEST_PLAIN_PATTERN,
    ):
        match = pattern.fullmatch(cleaned)
        if match is None:
            continue

        addressed_bot = match.groupdict().get("bot")
        if (
            addressed_bot
            and expected_username
            and addressed_bot.casefold() != expected_username
        ):
            return None

        character_name = match.group("name").strip()
        return character_name or None

    return None


def _caller_user_id(message: Message) -> int | None:
    caller = message.guest_bot_caller_user or message.from_user
    return caller.id if caller else None


async def _build_save_response(
    message: Message,
    character_name: str,
    database: Database,
) -> str:
    source_message = message.reply_to_message
    if source_message is None:
        return (
            "Команда должна быть отправлена ответом на изображение.\n\n"
            "Нажмите «Ответить» на фото или графический файл и снова "
            "вызовите бота."
        )

    media = extract_image(source_message)
    if media is None:
        return (
            "В сообщении, на которое вы ответили, нет поддерживаемого изображения.\n"
            "Сейчас принимаются фотографии и изображения, отправленные как файл."
        )

    try:
        character = await database.get_character(character_name)
    except ValueError as error:
        return escape(str(error))

    if character is None:
        return (
            "Такой персонаж не найден.\n\n"
            "Сначала создайте профиль в чате с ботом: "
            "<code>/create Каин</code>."
        )

    result = await database.save_character_media(
        character,
        media,
        saved_by=_caller_user_id(message),
        saved_in_chat=message.chat.id,
        source_chat_id=source_message.chat.id,
        source_message_id=source_message.message_id,
        source_thread_id=source_message.message_thread_id,
        command_message_id=message.message_id,
    )

    safe_character_name = escape(character.name)
    safe_storage_name = escape(result.storage_file_name)

    if not result.character_link_created:
        return (
            "Это изображение уже находится в архиве персонажа "
            f"<b>{safe_character_name}</b>.\n"
            f"Файл: <code>{safe_storage_name}</code>"
        )

    if result.media_created:
        status = "Новое изображение добавлено в архив."
    else:
        status = "Изображение уже было в общем архиве и привязано к персонажу."

    return (
        f"<b>{status}</b>\n\n"
        f"Персонаж: <b>{safe_character_name}</b>\n"
        f"Файл: <code>{safe_storage_name}</code>"
    )


async def _answer_guest_message(message: Message, text: str) -> None:
    if not message.guest_query_id:
        logger.error("Guest message received without guest_query_id")
        return

    result_id = hashlib.sha256(
        message.guest_query_id.encode("utf-8")
    ).hexdigest()[:32]

    await message.answer_guest_query(
        InlineQueryResultArticle(
            id=result_id,
            title="Velvet Archive",
            input_message_content=InputTextMessageContent(
                message_text=text,
                parse_mode=ParseMode.HTML,
            ),
        )
    )


@router.message(Command("save"))
async def handle_save_image(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer(
            "Укажите имя персонажа после команды.\n\n"
            "Ответьте на изображение командой "
            "<code>/save Каин</code>."
        )
        return

    response = await _build_save_response(message, command.args, database)
    await message.answer(response)


@router.guest_message()
async def handle_guest_save_image(
    message: Message,
    database: Database,
    bot_username: str,
) -> None:
    request_text = message.text or message.caption or ""
    character_name = parse_guest_save_character(request_text, bot_username)

    if character_name is None:
        safe_username = escape(bot_username or "имя_бота")
        await _answer_guest_message(
            message,
            "Не удалось распознать команду сохранения.\n\n"
            "Ответьте на изображение и отправьте:\n"
            f"<code>@{safe_username} save Каин</code>\n"
            "или\n"
            f"<code>/save@{safe_username} Каин</code>",
        )
        return

    try:
        response = await _build_save_response(
            message,
            character_name,
            database,
        )
    except Exception:
        logger.exception("Guest image save failed")
        response = (
            "Не удалось сохранить изображение из-за внутренней ошибки. "
            "Проверьте подключение к базе и журнал бота."
        )

    await _answer_guest_message(message, response)

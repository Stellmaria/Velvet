from __future__ import annotations

import logging
import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.database import Character, Database, SaveMediaResult
from velvet_bot.media import MediaDescriptor, extract_media, send_media_to_topic

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
    """Extract a character name from command, mention, or Guest Mode text."""
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
    caller = message.from_user or message.guest_bot_caller_user
    return caller.id if caller else None


def _is_character_archive_source(message: Message, character: Character) -> bool:
    return (
        character.archive_chat_id is not None
        and character.archive_thread_id is not None
        and message.chat.id == character.archive_chat_id
        and message.message_thread_id == character.archive_thread_id
    )


async def _place_media_in_character_topic(
    *,
    bot: Bot,
    database: Database,
    character: Character,
    media: MediaDescriptor,
    source_message: Message,
    result: SaveMediaResult,
    audit_logger: TelegramAuditLogger,
) -> tuple[bool, str | None]:
    if character.archive_chat_id is None or character.archive_thread_id is None:
        return False, "У персонажа не назначена тема архива."

    if _is_character_archive_source(source_message, character):
        if result.archive_message_id is None:
            await database.set_archive_message_id(
                character.id,
                result.media_id,
                source_message.message_id,
            )
        return False, None

    if result.archive_message_id is not None:
        return False, None

    try:
        archived_message = await send_media_to_topic(
            bot,
            media,
            chat_id=character.archive_chat_id,
            thread_id=character.archive_thread_id,
        )
        await database.set_archive_message_id(
            character.id,
            result.media_id,
            archived_message.message_id,
        )
        await audit_logger.send(
            "Медиа отправлено в ветку",
            level="SUCCESS",
            character=character.name,
            file=media.storage_file_name,
            media_type=media.media_type,
            archive_chat_id=character.archive_chat_id,
            archive_thread_id=character.archive_thread_id,
            archive_message_id=archived_message.message_id,
        )
    except Exception as error:
        logger.exception(
            "Failed to send media to archive topic for character %s",
            character.id,
        )
        await audit_logger.error(
            "Ошибка отправки медиа в ветку",
            error,
            character=character.name,
            file=media.storage_file_name,
            archive_chat_id=character.archive_chat_id,
            archive_thread_id=character.archive_thread_id,
        )
        return False, str(error)

    return True, None


async def _build_save_response(
    message: Message,
    character_name: str,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
) -> str:
    source_message = message.reply_to_message
    if source_message is None:
        return (
            "Команда должна быть отправлена ответом на фото или видео.\n\n"
            "Нажмите «Ответить» на медиафайл и снова вызовите бота."
        )

    media = extract_media(source_message)
    if media is None:
        return (
            "В сообщении, на которое вы ответили, нет поддерживаемого медиафайла.\n"
            "Сейчас принимаются фото, видео, анимации и изображения/видео как файл."
        )

    try:
        character = await database.get_character(character_name)
    except ValueError as error:
        return escape(str(error))

    if character is None:
        return (
            "Такой персонаж не найден.\n\n"
            "Сначала создайте профиль в чате с ботом: "
            "<code>/create Имя ссылка_на_тему</code>."
        )

    archive_message_id = (
        source_message.message_id
        if _is_character_archive_source(source_message, character)
        else None
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
        archive_message_id=archive_message_id,
    )

    if result.character_link_created:
        await audit_logger.send(
            "Медиа добавлено в архив",
            level="SUCCESS",
            character=character.name,
            file=result.storage_file_name,
            media_type=media.media_type,
            saved_by=_caller_user_id(message),
            saved_in_chat=message.chat.id,
            source_chat_id=source_message.chat.id,
            source_message_id=source_message.message_id,
        )

    uploaded_to_topic, upload_error = await _place_media_in_character_topic(
        bot=bot,
        database=database,
        character=character,
        media=media,
        source_message=source_message,
        result=result,
        audit_logger=audit_logger,
    )

    safe_character_name = escape(character.name)
    safe_storage_name = escape(result.storage_file_name)

    if not result.character_link_created:
        status = "Этот медиафайл уже находится в архиве персонажа."
    elif result.media_created:
        status = "Новый медиафайл добавлен в архив."
    else:
        status = "Медиафайл уже был в общем архиве и привязан к персонажу."

    details = [
        f"<b>{status}</b>",
        "",
        f"Персонаж: <b>{safe_character_name}</b>",
        f"Файл: <code>{safe_storage_name}</code>",
    ]

    if uploaded_to_topic:
        details.append("Тема: <b>копия отправлена</b>")
    elif upload_error == "У персонажа не назначена тема архива.":
        details.append(
            "Тема: <b>не назначена</b>. Используйте "
            "<code>/topic Имя ссылка</code>."
        )
    elif upload_error:
        details.append(
            "Тема: <b>не удалось отправить копию</b>\n"
            f"<code>{escape(upload_error)}</code>"
        )
    elif character.archive_topic_url:
        details.append("Тема: <b>медиа уже находится в архивной ветке</b>")

    return "\n".join(details)


async def _handle_normal_save(
    message: Message,
    character_name: str,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
) -> None:
    try:
        response = await _build_save_response(
            message,
            character_name,
            database,
            bot,
            audit_logger,
        )
    except Exception as error:
        logger.exception("Media save failed")
        await audit_logger.error(
            "Ошибка сохранения медиа",
            error,
            character=character_name,
            chat_id=message.chat.id,
            message_id=message.message_id,
            user_id=_caller_user_id(message),
        )
        response = "Не удалось сохранить медиафайл из-за внутренней ошибки."
    await message.answer(response)


@router.message(Command("save"))
async def handle_save_media(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
) -> None:
    if not command.args:
        await message.answer(
            "Укажите имя персонажа после команды.\n\n"
            "Ответьте на фото или видео командой <code>/save Аид</code>."
        )
        return

    await _handle_normal_save(
        message,
        command.args,
        database,
        bot,
        audit_logger,
    )


@router.message(F.text.regexp(r"^@[A-Za-z0-9_]+\s+/?save\s+.+$"))
async def handle_mention_save_media(
    message: Message,
    database: Database,
    bot_username: str,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
) -> None:
    character_name = parse_guest_save_character(message.text or "", bot_username)
    if character_name is None:
        return
    await _handle_normal_save(
        message,
        character_name,
        database,
        bot,
        audit_logger,
    )


@router.message()
async def handle_new_archive_topic_media(
    message: Message,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
) -> None:
    if message.message_thread_id is None:
        return

    bot_info = await bot.get_me()
    if message.from_user and message.from_user.id == bot_info.id:
        return

    media = extract_media(message)
    if media is None:
        return

    character = await database.get_character_by_archive_topic(
        message.chat.id,
        message.message_thread_id,
    )
    if character is None:
        return

    try:
        result = await database.save_character_media(
            character,
            media,
            saved_by=message.from_user.id if message.from_user else None,
            saved_in_chat=message.chat.id,
            source_chat_id=message.chat.id,
            source_message_id=message.message_id,
            source_thread_id=message.message_thread_id,
            command_message_id=None,
            archive_message_id=message.message_id,
        )
        logger.info(
            "Automatically archived topic media for character %s from %s/%s",
            character.id,
            message.chat.id,
            message.message_thread_id,
        )
        if result.character_link_created:
            await audit_logger.send(
                "Новое медиа принято из ветки",
                level="SUCCESS",
                character=character.name,
                file=result.storage_file_name,
                media_type=media.media_type,
                archive_chat_id=message.chat.id,
                archive_thread_id=message.message_thread_id,
                archive_message_id=message.message_id,
            )
    except Exception as error:
        logger.exception(
            "Failed to automatically archive topic media for character %s",
            character.id,
        )
        await audit_logger.error(
            "Ошибка автоматического архива ветки",
            error,
            character=character.name,
            archive_chat_id=message.chat.id,
            archive_thread_id=message.message_thread_id,
            archive_message_id=message.message_id,
        )

from __future__ import annotations

import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from velvet_bot.archive_topic_links import list_characters_by_archive_topic
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.database import Database
from velvet_bot.media import MediaDescriptor, extract_media
from velvet_bot.media_preview_persistence import set_media_preview
from velvet_bot.services.media_save import save_media_from_message

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_GUEST_COMMAND_PATTERN = re.compile(
    r"^/save(?:@(?P<bot>[A-Za-z0-9_]+))?\s+(?P<name>.+)$",
    re.IGNORECASE,
)
_GUEST_MENTION_PREFIX_PATTERN = re.compile(
    r"^@(?P<bot>[A-Za-z0-9_]+)\s+/?save\s+(?P<name>.+)$",
    re.IGNORECASE,
)
_GUEST_MENTION_AFTER_SAVE_PATTERN = re.compile(
    r"^/?save\s+@(?P<bot>[A-Za-z0-9_]+)\s+(?P<name>.+)$",
    re.IGNORECASE,
)
_GUEST_MENTION_SUFFIX_PATTERN = re.compile(
    r"^/?save\s+(?P<name>.+?)\s+@(?P<bot>[A-Za-z0-9_]+)$",
    re.IGNORECASE,
)
_GUEST_PLAIN_PATTERN = re.compile(r"^/?save\s+(?P<name>.+)$", re.IGNORECASE)
_MENTION_SAVE_FILTER = re.compile(
    r"^(?:"
    r"@[A-Za-z0-9_]+\s+/?save\s+.+|"
    r"/?save\s+@[A-Za-z0-9_]+\s+.+|"
    r"/?save\s+.+\s+@[A-Za-z0-9_]+"
    r")$",
    re.IGNORECASE,
)


def parse_guest_save_character(text: str, bot_username: str) -> str | None:
    cleaned = " ".join(text.split())
    if not cleaned:
        return None
    expected_username = bot_username.lstrip("@").casefold()
    for pattern in (
        _GUEST_COMMAND_PATTERN,
        _GUEST_MENTION_PREFIX_PATTERN,
        _GUEST_MENTION_AFTER_SAVE_PATTERN,
        _GUEST_MENTION_SUFFIX_PATTERN,
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


async def _persist_descriptor_preview(
    database: Database,
    *,
    media_id: int,
    media: MediaDescriptor,
) -> None:
    """Compatibility facade used by regression tests and legacy callers."""
    if not media.preview_file_id:
        return
    await set_media_preview(
        database,
        media_id=media_id,
        file_id=media.preview_file_id,
        file_unique_id=media.preview_file_unique_id,
        width=media.preview_width,
        height=media.preview_height,
        source=media.preview_source or "source_thumbnail",
    )


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
    return await save_media_from_message(
        database,
        bot,
        audit_logger,
        request_message=message,
        source_message=source_message,
        character_name=character_name,
        actor_id=_caller_user_id(message),
    )


async def _handle_normal_save(
    message: Message,
    character_name: str,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
) -> None:
    await message.answer(
        await _build_save_response(
            message,
            character_name,
            database,
            bot,
            audit_logger,
        )
    )


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


@router.message(F.text.regexp(_MENTION_SAVE_FILTER))
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
    characters = await list_characters_by_archive_topic(
        database,
        archive_chat_id=message.chat.id,
        archive_thread_id=message.message_thread_id,
    )
    if not characters:
        return

    for character in characters:
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
            await _persist_descriptor_preview(
                database,
                media_id=result.media_id,
                media=media,
            )
            logger.info(
                "Automatically archived topic media for character %s from %s/%s",
                character.id,
                message.chat.id,
                message.message_thread_id,
            )
            if result.character_link_created:
                await audit_logger.send(
                    "Новое медиа принято из общей ветки",
                    level="SUCCESS",
                    character=character.name,
                    file=result.storage_file_name,
                    media_type=media.media_type,
                    archive_chat_id=message.chat.id,
                    archive_thread_id=message.message_thread_id,
                    archive_message_id=message.message_id,
                    linked_characters=len(characters),
                )
        except Exception as error:  # p2-approved-boundary: report-topic-auto-archive-failure
            logger.exception(
                "Failed to automatically archive topic media for character %s",
                character.id,
            )
            await audit_logger.error(
                "Ошибка автоматического архива общей ветки",
                error,
                character=character.name,
                archive_chat_id=message.chat.id,
                archive_thread_id=message.message_thread_id,
                archive_message_id=message.message_id,
            )

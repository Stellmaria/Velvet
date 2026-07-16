from __future__ import annotations

import logging
from html import escape

from aiogram import Bot
from aiogram.types import Message

from velvet_bot.archive_catalog import set_archive_media_spoiler
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.database import Character, Database, SaveMediaResult
from velvet_bot.media import MediaDescriptor, extract_media, send_media_to_topic
from velvet_bot.media_preview_persistence import set_media_preview

logger = logging.getLogger(__name__)


async def save_media_from_message(
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    *,
    request_message: Message,
    source_message: Message,
    character_name: str,
    actor_id: int | None,
    spoiler: bool = False,
) -> str:
    try:
        return await _save_media_from_message(
            database,
            bot,
            audit_logger,
            request_message=request_message,
            source_message=source_message,
            character_name=character_name,
            actor_id=actor_id,
            spoiler=spoiler,
        )
    except Exception as error:
        logger.exception("Media save failed")
        await audit_logger.error(
            "Ошибка сохранения медиа",
            error,
            character=character_name,
            chat_id=request_message.chat.id,
            message_id=request_message.message_id,
            user_id=actor_id,
        )
        return "Не удалось сохранить медиафайл из-за внутренней ошибки."


async def _save_media_from_message(
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    *,
    request_message: Message,
    source_message: Message,
    character_name: str,
    actor_id: int | None,
    spoiler: bool,
) -> str:
    media = extract_media(source_message)
    if media is None:
        return (
            "В сообщении нет поддерживаемого медиафайла. "
            "Принимаются фото, видео, анимации и изображения/видео как файл."
        )
    character = await database.get_character(character_name)
    if character is None:
        return "Такой персонаж не найден. Сначала создайте его профиль."

    source_is_archive = _is_character_archive_source(source_message, character)
    result = await database.save_character_media(
        character,
        media,
        saved_by=actor_id,
        saved_in_chat=request_message.chat.id,
        source_chat_id=source_message.chat.id,
        source_message_id=source_message.message_id,
        source_thread_id=source_message.message_thread_id,
        command_message_id=request_message.message_id,
        archive_message_id=(source_message.message_id if source_is_archive else None),
    )
    await _persist_preview(database, result.media_id, media)

    if result.character_link_created:
        await audit_logger.send(
            "Медиа добавлено в архив",
            level="SUCCESS",
            character=character.name,
            file=result.storage_file_name,
            media_type=media.media_type,
            saved_by=actor_id,
            saved_in_chat=request_message.chat.id,
            source_chat_id=source_message.chat.id,
            source_message_id=source_message.message_id,
        )

    uploaded, upload_error = await _place_in_topic(
        bot,
        database,
        audit_logger,
        character=character,
        media=media,
        source_message=source_message,
        result=result,
    )

    spoiler_changed = False
    if spoiler:
        spoiler_changed = await set_archive_media_spoiler(
            database,
            character_id=character.id,
            media_id=result.media_id,
            is_spoiler=True,
        )
        if spoiler_changed:
            await audit_logger.send(
                "Материал отмечен как спойлер",
                level="SUCCESS",
                character=character.name,
                media_unique_id=media.telegram_file_unique_id,
                changed_by=actor_id,
            )

    if not result.character_link_created:
        status = "Этот медиафайл уже находится в архиве персонажа."
    elif result.media_created:
        status = "Новый медиафайл добавлен в архив."
    else:
        status = "Медиафайл уже был в общем архиве и привязан к персонажу."

    details = [
        f"<b>{status}</b>",
        "",
        f"Персонаж: <b>{escape(character.name)}</b>",
        f"Файл: <code>{escape(result.storage_file_name)}</code>",
    ]
    if uploaded:
        details.append("Тема: <b>копия отправлена</b>")
    elif upload_error == "У персонажа не назначена тема архива.":
        details.append("Тема: <b>не назначена</b>.")
    elif upload_error:
        details.append(
            "Тема: <b>не удалось отправить копию</b>\n"
            f"<code>{escape(upload_error)}</code>"
        )
    elif character.archive_topic_url:
        details.append("Тема: <b>медиа уже находится в архивной ветке</b>")
    if spoiler and spoiler_changed:
        details.append("Спойлер: <b>включён</b>.")
    return "\n".join(details)


def _is_character_archive_source(message: Message, character: Character) -> bool:
    return bool(
        character.archive_chat_id is not None
        and character.archive_thread_id is not None
        and message.chat.id == character.archive_chat_id
        and message.message_thread_id == character.archive_thread_id
    )


async def _persist_preview(
    database: Database,
    media_id: int,
    media: MediaDescriptor,
) -> None:
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


async def _place_in_topic(
    bot: Bot,
    database: Database,
    audit_logger: TelegramAuditLogger,
    *,
    character: Character,
    media: MediaDescriptor,
    source_message: Message,
    result: SaveMediaResult,
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
        logger.exception("Failed to send media to archive topic")
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


__all__ = ("save_media_from_message",)

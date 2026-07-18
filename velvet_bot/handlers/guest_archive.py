from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from html import escape

from aiogram import Bot, Router
from aiogram.enums import ParseMode
from aiogram.types import (
    ExternalReplyInfo,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)

from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.database import Character, Database
from velvet_bot.handlers.archive import parse_guest_save_character
from velvet_bot.media import MediaDescriptor, extract_media, send_media_to_topic

router = Router(name=__name__)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GuestSource:
    media_source: Message | ExternalReplyInfo
    source_chat_id: int
    source_message_id: int
    source_thread_id: int | None


class _GuestArchiveDeliveryReported(RuntimeError):
    """Internal signal that the delivery failure already reached the audit log."""


def _resolve_guest_source(message: Message) -> GuestSource | None:
    if message.reply_to_message is not None:
        source = message.reply_to_message
        return GuestSource(
            media_source=source,
            source_chat_id=source.chat.id,
            source_message_id=source.message_id,
            source_thread_id=source.message_thread_id,
        )

    if message.external_reply is not None:
        source = message.external_reply
        return GuestSource(
            media_source=source,
            source_chat_id=source.chat.id if source.chat else message.chat.id,
            source_message_id=(
                source.message_id
                if source.message_id is not None
                else message.message_id
            ),
            source_thread_id=None,
        )

    return None


def _caller_user_id(message: Message) -> int | None:
    caller = message.from_user or message.guest_bot_caller_user
    return caller.id if caller else None


async def _send_guest_answer(message: Message, text: str) -> None:
    if not message.guest_query_id:
        logger.error("Guest update has no guest_query_id")
        return

    result_id = hashlib.sha256(
        f"velvet:{message.guest_query_id}".encode("utf-8")
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


async def _archive_guest_media(
    *,
    message: Message,
    database: Database,
    bot: Bot,
    character: Character,
    media: MediaDescriptor,
    source: GuestSource,
    audit_logger: TelegramAuditLogger,
) -> str:
    result = await database.save_character_media(
        character,
        media,
        saved_by=_caller_user_id(message),
        saved_in_chat=message.chat.id,
        source_chat_id=source.source_chat_id,
        source_message_id=source.source_message_id,
        source_thread_id=source.source_thread_id,
        command_message_id=message.message_id,
        archive_message_id=None,
    )

    if result.character_link_created:
        await audit_logger.send(
            "Медиа добавлено через Guest Mode",
            level="SUCCESS",
            character=character.name,
            file=result.storage_file_name,
            media_type=media.media_type,
            saved_by=_caller_user_id(message),
            guest_chat_id=message.chat.id,
            source_chat_id=source.source_chat_id,
            source_message_id=source.source_message_id,
        )

    uploaded = False
    if (
        character.archive_chat_id is not None
        and character.archive_thread_id is not None
        and result.archive_message_id is None
    ):
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
            uploaded = True
            await audit_logger.send(
                "Guest-медиа отправлено в ветку",
                level="SUCCESS",
                character=character.name,
                file=result.storage_file_name,
                archive_chat_id=character.archive_chat_id,
                archive_thread_id=character.archive_thread_id,
                archive_message_id=archived_message.message_id,
            )
        except Exception as error:  # p2-approved-boundary: report-guest-topic-delivery-failure
            await audit_logger.error(
                "Ошибка отправки Guest-медиа в ветку",
                error,
                character=character.name,
                file=result.storage_file_name,
                archive_chat_id=character.archive_chat_id,
                archive_thread_id=character.archive_thread_id,
            )
            raise _GuestArchiveDeliveryReported(str(error)) from error

    if not result.character_link_created:
        status = "Этот файл уже был сохранён для персонажа."
    elif result.media_created:
        status = "Файл сохранён."
    else:
        status = "Файл привязан к персонажу."

    if uploaded:
        status += " Копия отправлена в его ветку."
    elif character.archive_chat_id is None:
        status += " Ветка архива не назначена."

    return status


@router.guest_message()
async def handle_guest_archive(
    message: Message,
    database: Database,
    bot: Bot,
    bot_username: str,
    audit_logger: TelegramAuditLogger,
) -> None:
    caller = message.from_user or message.guest_bot_caller_user
    logger.info(
        "Guest request received: query=%s caller_id=%s username=%s "
        "reply=%s external_reply=%s text=%r",
        bool(message.guest_query_id),
        caller.id if caller else None,
        caller.username if caller else None,
        message.reply_to_message is not None,
        message.external_reply is not None,
        message.text or message.caption or "",
    )

    request_text = message.text or message.caption or ""
    character_name = parse_guest_save_character(request_text, bot_username)
    if character_name is None:
        await _send_guest_answer(
            message,
            "Не удалось распознать команду.\n\n"
            f"Используйте: <code>@{escape(bot_username)} save Аид</code>",
        )
        return

    source = _resolve_guest_source(message)
    if source is None:
        await _send_guest_answer(
            message,
            "Команда должна быть отправлена ответом на фото, видео или файл.",
        )
        return

    media = extract_media(source.media_source)
    if media is None:
        await _send_guest_answer(
            message,
            "В сообщении нет поддерживаемого фото или видео.",
        )
        return

    try:
        character = await database.get_character(character_name)
        if character is None:
            await _send_guest_answer(
                message,
                f"Персонаж <b>{escape(character_name)}</b> не найден.",
            )
            return

        status = await _archive_guest_media(
            message=message,
            database=database,
            bot=bot,
            character=character,
            media=media,
            source=source,
            audit_logger=audit_logger,
        )
        await _send_guest_answer(
            message,
            f"<b>{escape(status)}</b>\n"
            f"Персонаж: <b>{escape(character.name)}</b>",
        )
    except Exception as error:  # p2-approved-boundary: report-guest-request-failure
        logger.exception("Guest archive request failed")
        if not isinstance(error, _GuestArchiveDeliveryReported):
            await audit_logger.error(
                "Ошибка Guest Mode",
                error,
                character=character_name,
                caller_id=_caller_user_id(message),
                guest_chat_id=message.chat.id,
                source_chat_id=source.source_chat_id,
                source_message_id=source.source_message_id,
            )
        await _send_guest_answer(
            message,
            "Не удалось сохранить файл.\n"
            f"<code>{escape(str(error))}</code>",
        )

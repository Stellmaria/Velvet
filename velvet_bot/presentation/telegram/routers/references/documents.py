from __future__ import annotations

import hashlib
import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    Document,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)

from velvet_bot.access import get_caller_user
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.database import Character, Database
from velvet_bot.presentation.telegram.routers.references.parsing import (
    parse_reference_add_character,
)
from velvet_bot.reference_catalog import add_character_reference
from velvet_bot.reference_media import prepare_reference_source, validate_reference_document
from velvet_bot.reference_uploads import ReferenceUploadSessions

router = Router(name=__name__)

_REFADD_GUEST_FILTER = re.compile(
    r"^(?:"
    r"/refadd(?:@[A-Za-z0-9_]+)?\s+.+|"
    r"@[A-Za-z0-9_]+\s+/?refadd\s+.+|"
    r"/?refadd\s+@[A-Za-z0-9_]+\s+.+|"
    r"/?refadd\s+.+\s+@[A-Za-z0-9_]+"
    r")$",
    re.IGNORECASE,
)
_REFADD_MENTION_FILTER = re.compile(
    r"^(?:"
    r"@[A-Za-z0-9_]+\s+/?refadd\s+.+|"
    r"/?refadd\s+@[A-Za-z0-9_]+\s+.+|"
    r"/?refadd\s+.+\s+@[A-Za-z0-9_]+"
    r")$",
    re.IGNORECASE,
)


async def _answer_guest_text(message: Message, text: str) -> None:
    if not message.guest_query_id:
        return
    result_id = hashlib.sha256(
        f"reference-document:{message.guest_query_id}:{text}".encode("utf-8")
    ).hexdigest()[:32]
    await message.answer_guest_query(
        InlineQueryResultArticle(
            id=result_id,
            title="Velvet References",
            input_message_content=InputTextMessageContent(
                message_text=text,
                parse_mode=ParseMode.HTML,
            ),
        )
    )


async def _store_document_reference(
    *,
    document: Document,
    character: Character,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    staging_chat_id: int | None,
    added_by: int | None,
) -> tuple[bool, int]:
    prepared = await prepare_reference_source(
        document,
        bot=bot,
        staging_chat_id=staging_chat_id,
    )
    result = await add_character_reference(
        database,
        character,
        prepared,
        added_by=added_by,
    )
    if result.created:
        await audit_logger.send(
            "Референс-документ персонажа добавлен",
            level="SUCCESS",
            character=character.name,
            reference_id=result.reference.id,
            total=result.total,
            added_by=added_by,
            original_file_name=document.file_name,
        )
    return result.created, result.total


async def _save_replied_document(
    *,
    message: Message,
    character_name: str,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
) -> str:
    source = message.reply_to_message
    document = source.document if source is not None else None
    if document is None:
        return "Ответьте командой на изображение, отправленное как документ."

    validation_error = validate_reference_document(document)
    if validation_error is not None:
        return validation_error

    try:
        character = await database.get_character(character_name)
    except ValueError as error:
        return escape(str(error))
    if character is None:
        return "Такой персонаж не найден."

    caller = get_caller_user(message)
    staging_chat_id = audit_logger.chat_id
    if staging_chat_id is None and not message.guest_query_id:
        staging_chat_id = message.chat.id

    try:
        created, total = await _store_document_reference(
            document=document,
            character=character,
            database=database,
            bot=bot,
            audit_logger=audit_logger,
            staging_chat_id=staging_chat_id,
            added_by=caller.id if caller else None,
        )
    except (ValueError, RuntimeError) as error:
        return escape(str(error))

    if created:
        return (
            f"✅ Референс <b>{escape(character.name)}</b> добавлен из документа. "
            f"Всего: <b>{total}</b>."
        )
    return (
        f"Этот референс уже сохранён у <b>{escape(character.name)}</b>. "
        f"Всего: <b>{total}</b>."
    )


@router.message(
    Command("refadd"),
    F.chat.type == ChatType.PRIVATE,
    F.reply_to_message.document,
)
async def handle_private_reference_document_start(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    reference_uploads: ReferenceUploadSessions,
) -> None:
    if not command.args:
        await message.answer("Укажите персонажа: <code>/refadd Аид</code>")
        return
    if message.from_user is None or message.reply_to_message is None:
        return

    document = message.reply_to_message.document
    if document is None:
        return
    validation_error = validate_reference_document(document)
    if validation_error is not None:
        await message.answer(validation_error)
        return

    character = await database.get_character(command.args)
    if character is None:
        await message.answer("Такой персонаж не найден.")
        return

    try:
        created, total = await _store_document_reference(
            document=document,
            character=character,
            database=database,
            bot=bot,
            audit_logger=audit_logger,
            staging_chat_id=audit_logger.chat_id or message.chat.id,
            added_by=message.from_user.id,
        )
    except (ValueError, RuntimeError) as error:
        await message.answer(escape(str(error)))
        return

    reference_uploads.start(
        message.from_user.id,
        character_id=character.id,
        character_name=character.name,
    )
    if created:
        reference_uploads.increment(message.from_user.id)

    status = (
        f"Документ сохранён как фотография. Всего: <b>{total}</b>."
        if created
        else f"Этот референс уже был сохранён. Всего: <b>{total}</b>."
    )
    await message.answer(
        f"<b>Загрузка референсов: {escape(character.name)}</b>\n\n"
        f"{status}\n\n"
        "Можно отправлять фотографии и изображения-документы JPG, PNG или WEBP.\n"
        "Завершение: <code>/refdone</code>"
    )


@router.message(
    Command("refadd"),
    F.chat.type != ChatType.PRIVATE,
    F.reply_to_message.document,
)
async def handle_group_reference_document(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
) -> None:
    if not command.args:
        await message.answer("Укажите персонажа: <code>/refadd Аид</code>")
        return
    await message.answer(
        await _save_replied_document(
            message=message,
            character_name=command.args,
            database=database,
            bot=bot,
            audit_logger=audit_logger,
        )
    )


@router.message(
    F.text.regexp(_REFADD_MENTION_FILTER),
    F.reply_to_message.document,
)
async def handle_reference_document_mention(
    message: Message,
    database: Database,
    bot_username: str,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
) -> None:
    character_name = parse_reference_add_character(message.text or "", bot_username)
    if character_name is None:
        return
    await message.answer(
        await _save_replied_document(
            message=message,
            character_name=character_name,
            database=database,
            bot=bot,
            audit_logger=audit_logger,
        )
    )


@router.guest_message(
    F.text.regexp(_REFADD_GUEST_FILTER),
    F.reply_to_message.document,
)
async def handle_guest_reference_document(
    message: Message,
    database: Database,
    bot_username: str,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
) -> None:
    character_name = parse_reference_add_character(
        message.text or message.caption or "",
        bot_username,
    )
    if character_name is None:
        return
    await _answer_guest_text(
        message,
        await _save_replied_document(
            message=message,
            character_name=character_name,
            database=database,
            bot=bot,
            audit_logger=audit_logger,
        ),
    )


@router.message(F.document, F.chat.type == ChatType.PRIVATE)
async def handle_reference_upload_document(
    message: Message,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    reference_uploads: ReferenceUploadSessions,
) -> None:
    if message.from_user is None or message.document is None:
        return
    session = reference_uploads.get(message.from_user.id)
    if session is None:
        return

    validation_error = validate_reference_document(message.document)
    if validation_error is not None:
        await message.answer(validation_error)
        return

    character = await database.get_character(session.character_name)
    if character is None:
        reference_uploads.stop(message.from_user.id)
        await message.answer("Персонаж больше не найден. Загрузка остановлена.")
        return

    try:
        created, total = await _store_document_reference(
            document=message.document,
            character=character,
            database=database,
            bot=bot,
            audit_logger=audit_logger,
            staging_chat_id=audit_logger.chat_id or message.chat.id,
            added_by=message.from_user.id,
        )
    except (ValueError, RuntimeError) as error:
        await message.answer(escape(str(error)))
        return

    if created:
        reference_uploads.increment(message.from_user.id)
    if message.media_group_id is None:
        await message.answer(
            (
                f"✅ Документ сохранён как фото-референс. Всего: <b>{total}</b>."
                if created
                else "Этот референс уже был добавлен."
            )
        )

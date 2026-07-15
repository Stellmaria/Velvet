from __future__ import annotations

from html import escape

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.database import Database
from velvet_bot.handlers.archive import _build_save_response
from velvet_bot.media import extract_media

router = Router(name=__name__)


@router.message(Command("save18"))
async def handle_save_spoiler_media(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
) -> None:
    if not command.args:
        await message.answer(
            "Ответьте на фото или видео командой "
            "<code>/save18 Имя</code>."
        )
        return
    source = message.reply_to_message
    media = extract_media(source) if source is not None else None
    if source is None or media is None:
        await message.answer(
            "Команда должна быть ответом на поддерживаемое фото или видео."
        )
        return

    response = await _build_save_response(
        message,
        command.args,
        database,
        bot,
        audit_logger,
    )
    character = await database.get_character(command.args)
    if character is None:
        await message.answer(response)
        return

    async with database._require_pool().acquire() as connection:
        updated = await connection.fetchval(
            """
            UPDATE character_media AS cm
            SET is_spoiler = TRUE
            FROM media_files AS mf
            WHERE cm.character_id = $1
              AND cm.media_id = mf.id
              AND mf.telegram_file_unique_id = $2
            RETURNING 1
            """,
            character.id,
            media.telegram_file_unique_id,
        )
    if updated is None:
        await message.answer(response)
        return

    await audit_logger.send(
        "Материал отмечен как спойлер",
        level="SUCCESS",
        character=character.name,
        media_unique_id=media.telegram_file_unique_id,
        changed_by=message.from_user.id if message.from_user else None,
    )
    await message.answer(
        response
        + "\nСпойлер: <b>включён</b>. В открытом архиве материал будет размыт."
    )

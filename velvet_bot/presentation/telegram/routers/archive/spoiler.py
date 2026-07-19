from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.database import Database
from velvet_bot.services.media_save import save_media_from_message

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
    if source is None:
        await message.answer(
            "Команда должна быть ответом на поддерживаемое фото или видео."
        )
        return
    response = await save_media_from_message(
        database,
        bot,
        audit_logger,
        request_message=message,
        source_message=source,
        character_name=command.args,
        actor_id=message.from_user.id if message.from_user else None,
        spoiler=True,
    )
    await message.answer(response)

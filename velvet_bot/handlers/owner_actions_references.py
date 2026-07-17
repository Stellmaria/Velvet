from __future__ import annotations

from html import escape

from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.types import Message

from velvet_bot.application.owner_references import (
    delete_reference_by_index,
    get_reference_page_by_name,
    start_reference_upload,
)
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.database import Database
from velvet_bot.reference_ui import build_reference_keyboard, format_reference_caption
from velvet_bot.reference_uploads import ReferenceUploadSessions


REFERENCE_ACTIONS = frozenset({"refadd", "refs", "refdel"})


async def handle_owner_reference_action(
    *,
    message: Message,
    owner_action: str,
    value: str,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    reference_uploads: ReferenceUploadSessions,
    actor_id: int | None,
) -> bool:
    if owner_action not in REFERENCE_ACTIONS:
        return False

    if owner_action == "refadd":
        if message.chat.type != ChatType.PRIVATE:
            raise ValueError("Загружайте референсы в личном чате с ботом.")
        if actor_id is None:
            raise ValueError("Не удалось определить владельца загрузки.")
        session = await start_reference_upload(
            database,
            reference_uploads,
            user_id=actor_id,
            character_name=value,
        )
        await message.answer(
            f"<b>Загрузка референсов: {escape(session.character_name)}</b>\n\n"
            "Отправляйте фотографии или альбом. Завершение и отмена доступны "
            "кнопками в разделе «Референсы»."
        )
        return True

    if owner_action == "refs":
        page = await get_reference_page_by_name(database, value)
        if page is None:
            raise ValueError("Такой персонаж не найден.")
        if page.reference is None:
            raise ValueError("У персонажа пока нет референсов.")
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=page.reference.telegram_file_id,
            caption=format_reference_caption(page),
            reply_markup=build_reference_keyboard(page),
        )
        return True

    result = await delete_reference_by_index(database, value)
    if result.reference is None:
        raise ValueError("Референс уже удалён.")
    await audit_logger.send(
        "Референс персонажа удалён",
        level="WARNING",
        character=result.character.name,
        reference_id=result.reference.id,
        remaining=result.remaining,
        deleted_by=actor_id,
    )
    await message.answer(
        f"🗑 Референс <b>{result.index}</b> персонажа "
        f"<b>{escape(result.character.name)}</b> удалён. "
        f"Осталось: <b>{result.remaining}</b>."
    )
    return True


__all__ = ("REFERENCE_ACTIONS", "handle_owner_reference_action")

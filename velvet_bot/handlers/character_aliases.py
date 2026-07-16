from __future__ import annotations

from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from velvet_bot.application.owner_profiles import (
    add_alias_from_text,
    delete_alias_from_text,
    list_aliases_from_text,
    rebuild_alias_index,
)
from velvet_bot.database import Database

router = Router(name=__name__)


@router.message(Command("aliasadd"))
async def handle_alias_add(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer(
            "Формат: <code>/aliasadd ИмяПерсонажа Алиас</code>\n"
            "Пример: <code>/aliasadd Каэль KaelLang</code>"
        )
        return
    try:
        item = await add_alias_from_text(
            database,
            command.args,
            actor_id=message.from_user.id if message.from_user else None,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    await message.answer(
        f"Алиас <code>#{escape(item.alias)}</code> назначен персонажу "
        f"<b>{escape(item.character_name)}</b>. Старые совпадающие посты пересчитаны."
    )


@router.message(Command("aliases"))
async def handle_alias_list(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer("Формат: <code>/aliases ИмяПерсонажа</code>")
        return
    try:
        character, items = await list_aliases_from_text(database, command.args)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    lines = [
        f"• <code>#{escape(item.alias)}</code>"
        + (" · основное имя" if item.source == "name" else "")
        for item in items
    ] or ["• алиасов пока нет"]
    await message.answer(
        f"<b>Алиасы: {escape(character.name)}</b>\n\n" + "\n".join(lines)
    )


@router.message(Command("aliasdel"))
async def handle_alias_delete(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer("Формат: <code>/aliasdel ИмяПерсонажа Алиас</code>")
        return
    try:
        result = await delete_alias_from_text(database, command.args)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    if not result.deleted:
        await message.answer(
            "Алиас не найден или это основное имя персонажа, которое удалять нельзя."
        )
        return
    await message.answer(
        f"Алиас <code>#{escape(result.alias)}</code> удалён у "
        f"<b>{escape(result.character.name)}</b>."
    )


@router.message(Command("aliasreindex"))
async def handle_alias_reindex(message: Message, database: Database) -> None:
    result = await rebuild_alias_index(database)
    await message.answer(
        "<b>Индекс хэштегов пересобран.</b>\n\n"
        f"Новых основных алиасов: <b>{result.created_name_aliases}</b>\n"
        f"Распознано связей: <b>{result.matched_links}</b> из "
        f"<b>{result.total_hashtags}</b>."
    )

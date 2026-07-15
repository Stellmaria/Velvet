from __future__ import annotations

from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from velvet_bot.character_aliases import (
    add_character_alias,
    delete_character_alias,
    ensure_name_aliases,
    list_character_aliases,
    rebuild_hashtag_character_links,
)
from velvet_bot.database import Database

router = Router(name=__name__)


@router.message(Command("aliasadd"))
async def handle_alias_add(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args or len(command.args.rsplit(maxsplit=1)) != 2:
        await message.answer(
            "Формат: <code>/aliasadd ИмяПерсонажа Алиас</code>\n"
            "Пример: <code>/aliasadd Каэль KaelLang</code>"
        )
        return
    character_name, alias = command.args.rsplit(maxsplit=1)
    character = await database.get_character(character_name)
    if character is None:
        await message.answer("Такой персонаж не найден.")
        return
    try:
        item = await add_character_alias(
            database,
            character_id=character.id,
            alias=alias,
            created_by=message.from_user.id if message.from_user else None,
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
    character = await database.get_character(command.args)
    if character is None:
        await message.answer("Такой персонаж не найден.")
        return
    items = await list_character_aliases(database, character_id=character.id)
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
    if not command.args or len(command.args.rsplit(maxsplit=1)) != 2:
        await message.answer(
            "Формат: <code>/aliasdel ИмяПерсонажа Алиас</code>"
        )
        return
    character_name, alias = command.args.rsplit(maxsplit=1)
    character = await database.get_character(character_name)
    if character is None:
        await message.answer("Такой персонаж не найден.")
        return
    deleted = await delete_character_alias(
        database,
        character_id=character.id,
        alias=alias,
    )
    if not deleted:
        await message.answer(
            "Алиас не найден или это основное имя персонажа, которое удалять нельзя."
        )
        return
    await message.answer(
        f"Алиас <code>#{escape(alias)}</code> удалён у "
        f"<b>{escape(character.name)}</b>."
    )


@router.message(Command("aliasreindex"))
async def handle_alias_reindex(message: Message, database: Database) -> None:
    created = await ensure_name_aliases(database)
    matched, total = await rebuild_hashtag_character_links(database)
    await message.answer(
        "<b>Индекс хэштегов пересобран.</b>\n\n"
        f"Новых основных алиасов: <b>{created}</b>\n"
        f"Распознано связей: <b>{matched}</b> из <b>{total}</b>."
    )

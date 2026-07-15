from __future__ import annotations

import re
from html import escape
from typing import TypeVar

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import InputMediaPhoto, Message

from velvet_bot.database import Character, Database
from velvet_bot.handlers.references import parse_reference_character
from velvet_bot.reference_catalog import (
    CharacterReference,
    ReferencePage,
    list_character_references,
)
from velvet_bot.reference_ui import build_reference_keyboard, format_reference_caption

router = Router(name=__name__)

_REF_MENTION_FILTER = re.compile(
    r"^(?:"
    r"@[A-Za-z0-9_]+\s+/?refs?\s+.+|"
    r"/?refs?\s+@[A-Za-z0-9_]+\s+.+|"
    r"/?refs?\s+.+\s+@[A-Za-z0-9_]+"
    r")$",
    re.IGNORECASE,
)

_T = TypeVar("_T")


def chunk_references(items: list[_T], size: int = 10) -> list[list[_T]]:
    safe_size = max(2, min(size, 10))
    return [items[index : index + safe_size] for index in range(0, len(items), safe_size)]


def _album_caption(
    character: Character,
    *,
    index: int,
    total: int,
) -> str:
    return (
        f"<b>{escape(character.name)}</b> · референс "
        f"<b>{index}</b> из <b>{total}</b>\n"
        f"Удалить: <code>/refdel {escape(character.name)} {index}</code>"
    )


async def send_reference_collection(
    *,
    bot: Bot,
    chat_id: int,
    character: Character,
    references: list[CharacterReference],
) -> None:
    total = len(references)
    if total == 0:
        raise ValueError("У персонажа пока нет референсов.")

    if total == 1:
        page = ReferencePage(
            character=character,
            reference=references[0],
            offset=0,
            total=1,
        )
        await bot.send_photo(
            chat_id=chat_id,
            photo=references[0].telegram_file_id,
            caption=format_reference_caption(page),
            reply_markup=build_reference_keyboard(page),
        )
        return

    sent_count = 0
    for batch in chunk_references(references):
        if len(batch) == 1:
            sent_count += 1
            await bot.send_photo(
                chat_id=chat_id,
                photo=batch[0].telegram_file_id,
                caption=_album_caption(
                    character,
                    index=sent_count,
                    total=total,
                ),
                parse_mode=ParseMode.HTML,
            )
            continue

        media: list[InputMediaPhoto] = []
        for reference in batch:
            sent_count += 1
            media.append(
                InputMediaPhoto(
                    media=reference.telegram_file_id,
                    caption=_album_caption(
                        character,
                        index=sent_count,
                        total=total,
                    ),
                    parse_mode=ParseMode.HTML,
                )
            )
        await bot.send_media_group(chat_id=chat_id, media=media)


async def _resolve_collection(
    database: Database,
    character_name: str,
) -> tuple[Character | None, list[CharacterReference]]:
    character = await database.get_character(character_name)
    if character is None:
        return None, []
    references = await list_character_references(database, character.id, limit=50)
    return character, references


@router.message(Command("refs", "ref"))
async def handle_reference_album_command(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
) -> None:
    if not command.args:
        await message.answer("Укажите персонажа: <code>/ref Аид</code>")
        return

    character, references = await _resolve_collection(database, command.args)
    if character is None:
        await message.answer("Такой персонаж не найден.")
        return
    if not references:
        await message.answer(
            "У персонажа пока нет референсов.\n\n"
            f"Добавление: <code>/refadd {escape(character.name)}</code>"
        )
        return

    await send_reference_collection(
        bot=bot,
        chat_id=message.chat.id,
        character=character,
        references=references,
    )


@router.message(F.text.regexp(_REF_MENTION_FILTER))
async def handle_reference_album_mention(
    message: Message,
    database: Database,
    bot_username: str,
    bot: Bot,
) -> None:
    character_name = parse_reference_character(message.text or "", bot_username)
    if character_name is None:
        return

    character, references = await _resolve_collection(database, character_name)
    if character is None:
        await message.answer("Такой персонаж не найден.")
        return
    if not references:
        await message.answer("У этого персонажа пока нет референсов.")
        return

    await send_reference_collection(
        bot=bot,
        chat_id=message.chat.id,
        character=character,
        references=references,
    )

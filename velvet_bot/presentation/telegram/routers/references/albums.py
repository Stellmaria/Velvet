from __future__ import annotations

import hashlib
import re
from html import escape
from typing import TypeVar

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InputMediaPhoto,
    InputTextMessageContent,
    Message,
)

from velvet_bot.database import Character, Database
from velvet_bot.reference_catalog import (
    CharacterReference,
    ReferencePage,
    list_character_references,
)
from velvet_bot.reference_ui import build_reference_keyboard, format_reference_caption
from velvet_bot.presentation.telegram.routers.references.parsing import (
    parse_reference_character,
    parse_reference_selector,
)

router = Router(name=__name__)

_REF_MENTION_FILTER = re.compile(
    r"^(?:"
    r"@[A-Za-z0-9_]+\s+/?refs?\s+.+|"
    r"/?refs?\s+@[A-Za-z0-9_]+\s+.+|"
    r"/?refs?\s+.+\s+@[A-Za-z0-9_]+"
    r")$",
    re.IGNORECASE,
)
_REF_INDEX_GUEST_FILTER = re.compile(
    r"^(?:"
    r"/refs?(?:@[A-Za-z0-9_]+)?\s+.+\s+#?\d+|"
    r"@[A-Za-z0-9_]+\s+/?refs?\s+.+\s+#?\d+|"
    r"/?refs?\s+@[A-Za-z0-9_]+\s+.+\s+#?\d+|"
    r"/?refs?\s+.+\s+#?\d+\s+@[A-Za-z0-9_]+"
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


def _reference_page(
    character: Character,
    references: list[CharacterReference],
    index: int,
) -> ReferencePage:
    return ReferencePage(
        character=character,
        reference=references[index - 1],
        offset=index - 1,
        total=len(references),
    )


async def send_reference_collection(
    *,
    bot: Bot,
    chat_id: int,
    character: Character,
    references: list[CharacterReference],
    selected_index: int | None = None,
) -> None:
    total = len(references)
    if total == 0:
        raise ValueError("У персонажа пока нет референсов.")

    if selected_index is not None:
        if selected_index < 1 or selected_index > total:
            raise IndexError(
                f"У персонажа {escape(character.name)} только {total} референс(а/ов)."
            )
        page = _reference_page(character, references, selected_index)
        await bot.send_photo(
            chat_id=chat_id,
            photo=page.reference.telegram_file_id,
            caption=format_reference_caption(page),
            reply_markup=build_reference_keyboard(page),
        )
        return

    if total == 1:
        page = _reference_page(character, references, 1)
        await bot.send_photo(
            chat_id=chat_id,
            photo=page.reference.telegram_file_id,
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
    request: str,
) -> tuple[Character | None, list[CharacterReference], int | None]:
    cleaned = " ".join(request.split())
    if not cleaned:
        return None, [], None

    # Preserve legitimate character names ending in a number.
    try:
        character = await database.get_character(cleaned)
    except ValueError:
        character = None
    if character is not None:
        references = await list_character_references(database, character.id, limit=50)
        return character, references, None

    character_name, selected_index = parse_reference_selector(cleaned)
    if selected_index is None:
        return None, [], None

    try:
        character = await database.get_character(character_name)
    except ValueError:
        character = None
    if character is None:
        return None, [], selected_index

    references = await list_character_references(database, character.id, limit=50)
    return character, references, selected_index


async def _answer_guest_text(message: Message, text: str) -> None:
    if not message.guest_query_id:
        return
    result_id = hashlib.sha256(
        f"reference-selection-text:{message.guest_query_id}:{text}".encode("utf-8")
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


async def _answer_guest_reference(message: Message, page: ReferencePage) -> None:
    if not message.guest_query_id or page.reference is None:
        return
    result_id = hashlib.sha256(
        f"reference-selection:{message.guest_query_id}:{page.reference.id}".encode(
            "utf-8"
        )
    ).hexdigest()[:32]
    await message.answer_guest_query(
        InlineQueryResultCachedPhoto(
            id=result_id,
            photo_file_id=page.reference.telegram_file_id,
            caption=format_reference_caption(page),
            parse_mode=ParseMode.HTML,
            reply_markup=build_reference_keyboard(page),
        )
    )


def _inline_photo_result(
    character: Character,
    references: list[CharacterReference],
    index: int,
) -> InlineQueryResultCachedPhoto:
    page = _reference_page(character, references, index)
    return InlineQueryResultCachedPhoto(
        id=f"ref-{page.reference.id}",
        photo_file_id=page.reference.telegram_file_id,
        caption=format_reference_caption(page),
        parse_mode=ParseMode.HTML,
        reply_markup=build_reference_keyboard(page),
    )


@router.message(Command("refs", "ref"))
async def handle_reference_album_command(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
) -> None:
    if not command.args:
        await message.answer(
            "Укажите персонажа: <code>/ref Аид</code>\n"
            "Один референс: <code>/ref Аид 2</code>"
        )
        return

    character, references, selected_index = await _resolve_collection(
        database,
        command.args,
    )
    if character is None:
        await message.answer("Такой персонаж не найден.")
        return
    if not references:
        await message.answer(
            "У персонажа пока нет референсов.\n\n"
            f"Добавление: <code>/refadd {escape(character.name)}</code>"
        )
        return

    try:
        await send_reference_collection(
            bot=bot,
            chat_id=message.chat.id,
            character=character,
            references=references,
            selected_index=selected_index,
        )
    except IndexError:
        await message.answer(
            f"У персонажа <b>{escape(character.name)}</b> всего "
            f"<b>{len(references)}</b> референс(а/ов).\n\n"
            f"Пример: <code>/ref {escape(character.name)} 1</code>"
        )


@router.message(F.text.regexp(_REF_MENTION_FILTER))
async def handle_reference_album_mention(
    message: Message,
    database: Database,
    bot_username: str,
    bot: Bot,
) -> None:
    request = parse_reference_character(message.text or "", bot_username)
    if request is None:
        return

    character, references, selected_index = await _resolve_collection(database, request)
    if character is None:
        await message.answer("Такой персонаж не найден.")
        return
    if not references:
        await message.answer("У этого персонажа пока нет референсов.")
        return

    try:
        await send_reference_collection(
            bot=bot,
            chat_id=message.chat.id,
            character=character,
            references=references,
            selected_index=selected_index,
        )
    except IndexError:
        await message.answer(
            f"У персонажа <b>{escape(character.name)}</b> всего "
            f"<b>{len(references)}</b> референс(а/ов)."
        )


@router.guest_message(F.text.regexp(_REF_INDEX_GUEST_FILTER))
async def handle_guest_reference_selection(
    message: Message,
    database: Database,
    bot_username: str,
) -> None:
    request = parse_reference_character(
        message.text or message.caption or "",
        bot_username,
    )
    if request is None:
        return

    character, references, selected_index = await _resolve_collection(database, request)
    if character is None:
        await _answer_guest_text(message, "Такой персонаж не найден.")
        return
    if not references:
        await _answer_guest_text(
            message,
            f"У персонажа <b>{escape(character.name)}</b> пока нет референсов.",
        )
        return

    # A real character name ending in a number wins over selector parsing.
    index = selected_index or 1
    if index < 1 or index > len(references):
        await _answer_guest_text(
            message,
            f"У персонажа <b>{escape(character.name)}</b> всего "
            f"<b>{len(references)}</b> референс(а/ов).",
        )
        return
    await _answer_guest_reference(message, _reference_page(character, references, index))


@router.inline_query(
    F.query.regexp(r"^\s*/?refs?\s+.+\s+#?\d+\s*$", flags=re.IGNORECASE)
)
async def handle_inline_reference_selection(
    query: InlineQuery,
    database: Database,
    bot_username: str,
) -> None:
    request = parse_reference_character(query.query, bot_username)
    if request is None:
        return

    character, references, selected_index = await _resolve_collection(database, request)
    if character is None or not references:
        await query.answer([], cache_time=1, is_personal=True)
        return

    if selected_index is None:
        results = [
            _inline_photo_result(character, references, index)
            for index in range(1, len(references) + 1)
        ]
        await query.answer(results, cache_time=1, is_personal=True)
        return

    if selected_index < 1 or selected_index > len(references):
        await query.answer(
            [
                InlineQueryResultArticle(
                    id="reference-index-not-found",
                    title="Референс не найден",
                    description=(
                        f"У {character.name} всего {len(references)} референс(а/ов)."
                    ),
                    input_message_content=InputTextMessageContent(
                        message_text=(
                            f"У персонажа <b>{escape(character.name)}</b> всего "
                            f"<b>{len(references)}</b> референс(а/ов)."
                        ),
                        parse_mode=ParseMode.HTML,
                    ),
                )
            ],
            cache_time=1,
            is_personal=True,
        )
        return

    await query.answer(
        [_inline_photo_result(character, references, selected_index)],
        cache_time=1,
        is_personal=True,
    )

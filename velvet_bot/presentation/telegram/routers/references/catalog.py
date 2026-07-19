from __future__ import annotations

import hashlib
import logging
import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InputMediaPhoto,
    InputTextMessageContent,
    Message,
)

from velvet_bot.application.owner_references import (
    finish_reference_upload,
    get_reference_page_by_name,
    start_reference_upload,
)
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.database import Character, Database
from velvet_bot.reference_catalog import (
    ReferencePage,
    add_character_reference,
    get_reference_page,
    list_character_references,
)
from velvet_bot.reference_ui import (
    ReferenceCallback,
    build_reference_keyboard,
    format_reference_caption,
)
from velvet_bot.reference_uploads import ReferenceUploadSessions

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_REF_COMMAND_PATTERN = re.compile(
    r"^/refs?(?:@(?P<bot>[A-Za-z0-9_]+))?\s+(?P<name>.+)$",
    re.IGNORECASE,
)
_REF_MENTION_PREFIX_PATTERN = re.compile(
    r"^@(?P<bot>[A-Za-z0-9_]+)\s+/?refs?\s+(?P<name>.+)$",
    re.IGNORECASE,
)
_REF_MENTION_AFTER_PATTERN = re.compile(
    r"^/?refs?\s+@(?P<bot>[A-Za-z0-9_]+)\s+(?P<name>.+)$",
    re.IGNORECASE,
)
_REF_MENTION_SUFFIX_PATTERN = re.compile(
    r"^/?refs?\s+(?P<name>.+?)\s+@(?P<bot>[A-Za-z0-9_]+)$",
    re.IGNORECASE,
)
_REF_PLAIN_PATTERN = re.compile(r"^/?refs?\s+(?P<name>.+)$", re.IGNORECASE)
_REF_GUEST_FILTER = re.compile(
    r"^(?:"
    r"/refs?(?:@[A-Za-z0-9_]+)?\s+.+|"
    r"@[A-Za-z0-9_]+\s+/?refs?\s+.+|"
    r"/?refs?\s+@[A-Za-z0-9_]+\s+.+|"
    r"/?refs?\s+.+\s+@[A-Za-z0-9_]+"
    r")$",
    re.IGNORECASE,
)
_REF_MENTION_FILTER = re.compile(
    r"^(?:"
    r"@[A-Za-z0-9_]+\s+/?refs?\s+.+|"
    r"/?refs?\s+@[A-Za-z0-9_]+\s+.+|"
    r"/?refs?\s+.+\s+@[A-Za-z0-9_]+"
    r")$",
    re.IGNORECASE,
)


def parse_reference_character(text: str, bot_username: str) -> str | None:
    cleaned = " ".join(text.split())
    if not cleaned:
        return None
    expected_username = bot_username.lstrip("@").casefold()
    for pattern in (
        _REF_COMMAND_PATTERN,
        _REF_MENTION_PREFIX_PATTERN,
        _REF_MENTION_AFTER_PATTERN,
        _REF_MENTION_SUFFIX_PATTERN,
        _REF_PLAIN_PATTERN,
    ):
        match = pattern.fullmatch(cleaned)
        if match is None:
            continue
        addressed_bot = match.groupdict().get("bot")
        if (
            addressed_bot
            and expected_username
            and addressed_bot.casefold() != expected_username
        ):
            return None
        character_name = match.group("name").strip()
        return character_name or None
    return None


async def _resolve_page_by_name(
    database: Database,
    character_name: str,
) -> ReferencePage | None:
    return await get_reference_page_by_name(database, character_name)


async def _send_reference_page(bot: Bot, chat_id: int, page: ReferencePage) -> Message:
    if page.reference is None:
        raise ValueError("У персонажа пока нет референсов.")
    return await bot.send_photo(
        chat_id=chat_id,
        photo=page.reference.telegram_file_id,
        caption=format_reference_caption(page),
        reply_markup=build_reference_keyboard(page),
    )


async def _answer_guest_reference(message: Message, page: ReferencePage) -> None:
    if not message.guest_query_id or page.reference is None:
        return
    result_id = hashlib.sha256(
        f"reference:{message.guest_query_id}:{page.reference.id}".encode("utf-8")
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


async def _answer_guest_text(message: Message, text: str) -> None:
    if not message.guest_query_id:
        return
    result_id = hashlib.sha256(
        f"reference-text:{message.guest_query_id}".encode("utf-8")
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


async def _add_photo_reference(
    *,
    database: Database,
    character: Character,
    message: Message,
    audit_logger: TelegramAuditLogger,
) -> tuple[bool, int]:
    if not message.photo:
        raise ValueError("Референсы нужно отправлять как фотографию, а не как документ.")
    photo = message.photo[-1]
    result = await add_character_reference(
        database,
        character,
        photo,
        added_by=message.from_user.id if message.from_user else None,
    )
    if result.created:
        await audit_logger.send(
            "Референс персонажа добавлен",
            level="SUCCESS",
            character=character.name,
            reference_id=result.reference.id,
            total=result.total,
            added_by=message.from_user.id if message.from_user else None,
        )
    return result.created, result.total


@router.message(Command("refadd"))
async def handle_reference_upload_start(
    message: Message,
    command: CommandObject,
    database: Database,
    reference_uploads: ReferenceUploadSessions,
    audit_logger: TelegramAuditLogger,
) -> None:
    if message.chat.type != ChatType.PRIVATE:
        await message.answer("Загружайте референсы в личном чате с ботом.")
        return
    if not command.args:
        await message.answer("Укажите персонажа. Пример: <code>/refadd Аид</code>")
        return
    if message.from_user is None:
        await message.answer("Не удалось определить владельца загрузки.")
        return
    try:
        session = await start_reference_upload(
            database,
            reference_uploads,
            user_id=message.from_user.id,
            character_name=command.args,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    character = await database.get_character(session.character_name)
    assert character is not None
    source = message.reply_to_message or message
    added_now = False
    total = None
    if source.photo:
        added_now, total = await _add_photo_reference(
            database=database,
            character=character,
            message=source,
            audit_logger=audit_logger,
        )
        if added_now:
            reference_uploads.increment(message.from_user.id)
    status = (
        f"\nТекущий референс сохранён. Всего: <b>{total}</b>."
        if added_now and total is not None
        else ""
    )
    await message.answer(
        f"<b>Загрузка референсов: {escape(session.character_name)}</b>\n\n"
        "Отправьте одну фотографию или целый альбом. Каждая фотография будет "
        "добавлена в профиль персонажа.\n\n"
        "Завершение и отмена доступны кнопками или резервными командами "
        "<code>/refdone</code> и <code>/refcancel</code>."
        f"{status}"
    )


@router.message(Command("refdone"))
async def handle_reference_upload_done(
    message: Message,
    reference_uploads: ReferenceUploadSessions,
) -> None:
    if message.from_user is None:
        return
    session = finish_reference_upload(reference_uploads, user_id=message.from_user.id)
    if session is None:
        await message.answer("Активной загрузки референсов нет.")
        return
    await message.answer(
        "<b>Загрузка завершена</b>\n\n"
        f"Персонаж: <b>{escape(session.character_name)}</b>\n"
        f"Добавлено за сеанс: <b>{session.added_count}</b>"
    )


@router.message(Command("refcancel"))
async def handle_reference_upload_cancel(
    message: Message,
    reference_uploads: ReferenceUploadSessions,
) -> None:
    if message.from_user is None:
        return
    session = finish_reference_upload(reference_uploads, user_id=message.from_user.id)
    await message.answer(
        "Загрузка референсов остановлена."
        if session is not None
        else "Активной загрузки референсов нет."
    )


@router.message(F.photo, F.chat.type == ChatType.PRIVATE)
async def handle_reference_upload_photo(
    message: Message,
    database: Database,
    reference_uploads: ReferenceUploadSessions,
    audit_logger: TelegramAuditLogger,
) -> None:
    if message.from_user is None:
        return
    session = reference_uploads.get(message.from_user.id)
    if session is None:
        return
    character = await database.get_character(session.character_name)
    if character is None:
        finish_reference_upload(reference_uploads, user_id=message.from_user.id)
        await message.answer("Персонаж больше не найден. Загрузка остановлена.")
        return
    created, total = await _add_photo_reference(
        database=database,
        character=character,
        message=message,
        audit_logger=audit_logger,
    )
    if created:
        reference_uploads.increment(message.from_user.id)
    if message.media_group_id is None:
        await message.answer(
            f"✅ Референс добавлен. Всего у персонажа: <b>{total}</b>."
            if created
            else "Этот референс уже был добавлен."
        )


@router.message(Command("refs", "ref"))
async def handle_show_references(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
) -> None:
    if not command.args:
        await message.answer("Укажите персонажа: <code>/refs Аид</code>")
        return
    try:
        page = await get_reference_page_by_name(database, command.args)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    if page is None:
        await message.answer("Такой персонаж не найден.")
        return
    if page.reference is None:
        await message.answer("У персонажа пока нет референсов.")
        return
    await _send_reference_page(bot, message.chat.id, page)


@router.message(F.text.regexp(_REF_MENTION_FILTER))
async def handle_reference_mention(
    message: Message,
    database: Database,
    bot_username: str,
    bot: Bot,
) -> None:
    character_name = parse_reference_character(message.text or "", bot_username)
    if character_name is None:
        return
    page = await _resolve_page_by_name(database, character_name)
    if page is None:
        await message.answer("Такой персонаж не найден.")
        return
    if page.reference is None:
        await message.answer("У этого персонажа пока нет референсов.")
        return
    await _send_reference_page(bot, message.chat.id, page)


@router.guest_message(F.text.regexp(_REF_GUEST_FILTER))
async def handle_guest_reference(
    message: Message,
    database: Database,
    bot_username: str,
) -> None:
    character_name = parse_reference_character(
        message.text or message.caption or "",
        bot_username,
    )
    if character_name is None:
        return
    page = await _resolve_page_by_name(database, character_name)
    if page is None:
        await _answer_guest_text(message, "Такой персонаж не найден.")
        return
    if page.reference is None:
        await _answer_guest_text(
            message,
            f"У персонажа <b>{escape(page.character.name)}</b> пока нет референсов.",
        )
        return
    await _answer_guest_reference(message, page)


@router.inline_query(F.query.regexp(r"^\s*/?refs?\s+.+$", flags=re.IGNORECASE))
async def handle_inline_references(
    query: InlineQuery,
    database: Database,
    bot_username: str,
) -> None:
    character_name = parse_reference_character(query.query, bot_username)
    if character_name is None:
        return
    character = await database.get_character(character_name)
    if character is None:
        await query.answer([], cache_time=1, is_personal=True)
        return
    references = await list_character_references(database, character.id, limit=50)
    total = len(references)
    results = [
        InlineQueryResultCachedPhoto(
            id=f"ref-{reference.id}",
            photo_file_id=reference.telegram_file_id,
            caption=(
                f"<b>{escape(character.name)}</b> · референс "
                f"<b>{index}</b> из <b>{total}</b>"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=build_reference_keyboard(
                ReferencePage(
                    character=character,
                    reference=reference,
                    offset=index - 1,
                    total=total,
                )
            ),
        )
        for index, reference in enumerate(references, start=1)
    ]
    await query.answer(results, cache_time=1, is_personal=True)


@router.callback_query(ReferenceCallback.filter())
async def handle_reference_callback(
    callback: CallbackQuery,
    callback_data: ReferenceCallback,
    database: Database,
    bot: Bot,
) -> None:
    if callback_data.action == "noop":
        await callback.answer()
        return
    page = await get_reference_page(
        database,
        callback_data.character_id,
        callback_data.offset,
    )
    if page is None:
        await callback.answer("Персонаж больше не найден.", show_alert=True)
        return
    if page.reference is None:
        await callback.answer("Референсы больше не найдены.", show_alert=True)
        return
    media = InputMediaPhoto(
        media=page.reference.telegram_file_id,
        caption=format_reference_caption(page),
        parse_mode=ParseMode.HTML,
    )
    keyboard = build_reference_keyboard(page)
    try:
        if callback.inline_message_id:
            await bot.edit_message_media(
                inline_message_id=callback.inline_message_id,
                media=media,
                reply_markup=keyboard,
            )
        elif isinstance(callback.message, Message):
            await callback.message.edit_media(media=media, reply_markup=keyboard)
        else:
            await callback.answer("Сообщение больше недоступно.", show_alert=True)
            return
    except TelegramBadRequest as error:
        logger.info("Reference media edit failed: %s", error)
        await callback.answer("Не удалось переключить референс.", show_alert=True)
        return
    await callback.answer()

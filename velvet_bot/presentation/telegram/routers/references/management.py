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
    InlineQueryResultArticle,
    InputMediaPhoto,
    InputTextMessageContent,
    Message,
    PhotoSize,
)

from velvet_bot.access import get_caller_user
from velvet_bot.application.owner_references import (
    delete_reference_by_index,
    parse_reference_index,
)
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.database import Character, Database
from velvet_bot.reference_catalog import (
    ReferencePage,
    add_character_reference,
    delete_character_reference,
    get_reference_page,
)
from velvet_bot.presentation.telegram.routers.references.parsing import (
    parse_reference_add_character,
)
from velvet_bot.reference_ui import (
    ReferenceCallback,
    build_reference_delete_keyboard,
    build_reference_keyboard,
    format_reference_caption,
)

router = Router(name=__name__)
logger = logging.getLogger(__name__)

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


def parse_reference_delete_args(value: str) -> tuple[str, int] | None:
    try:
        return parse_reference_index(value)
    except ValueError:
        return None


def _find_context_photo(message: Message) -> PhotoSize | None:
    source = message.reply_to_message
    if source is None and message.photo:
        source = message
    if source is None or not source.photo:
        return None
    return source.photo[-1]


async def _answer_guest_text(message: Message, text: str) -> None:
    if not message.guest_query_id:
        return
    result_id = hashlib.sha256(
        f"reference-management:{message.guest_query_id}:{text}".encode("utf-8")
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


async def _add_reference(
    *,
    database: Database,
    character: Character,
    photo: PhotoSize,
    added_by: int | None,
    audit_logger: TelegramAuditLogger,
) -> tuple[bool, int]:
    result = await add_character_reference(
        database,
        character,
        photo,
        added_by=added_by,
    )
    if result.created:
        await audit_logger.send(
            "Референс персонажа добавлен",
            level="SUCCESS",
            character=character.name,
            reference_id=result.reference.id,
            total=result.total,
            added_by=added_by,
        )
    return result.created, result.total


async def _save_context_reference(
    *,
    message: Message,
    character_name: str,
    database: Database,
    audit_logger: TelegramAuditLogger,
) -> str:
    photo = _find_context_photo(message)
    if photo is None:
        return (
            "Ответьте этой командой на фотографию. "
            "Файл должен быть отправлен как фото, а не как документ."
        )
    try:
        character = await database.get_character(character_name)
    except ValueError as error:
        return escape(str(error))
    if character is None:
        return "Такой персонаж не найден."
    caller = get_caller_user(message)
    created, total = await _add_reference(
        database=database,
        character=character,
        photo=photo,
        added_by=caller.id if caller else None,
        audit_logger=audit_logger,
    )
    if created:
        return (
            f"✅ Референс <b>{escape(character.name)}</b> добавлен. "
            f"Всего: <b>{total}</b>."
        )
    return (
        f"Этот референс уже сохранён у <b>{escape(character.name)}</b>. "
        f"Всего: <b>{total}</b>."
    )


@router.message(Command("refadd"), F.chat.type != ChatType.PRIVATE)
async def handle_group_reference_add(
    message: Message,
    command: CommandObject,
    database: Database,
    audit_logger: TelegramAuditLogger,
) -> None:
    if not command.args:
        await message.answer("Укажите персонажа: <code>/refadd Аид</code>")
        return
    await message.answer(
        await _save_context_reference(
            message=message,
            character_name=command.args,
            database=database,
            audit_logger=audit_logger,
        )
    )


@router.message(F.text.regexp(_REFADD_MENTION_FILTER))
async def handle_reference_add_mention(
    message: Message,
    database: Database,
    bot_username: str,
    audit_logger: TelegramAuditLogger,
) -> None:
    character_name = parse_reference_add_character(message.text or "", bot_username)
    if character_name is None:
        return
    await message.answer(
        await _save_context_reference(
            message=message,
            character_name=character_name,
            database=database,
            audit_logger=audit_logger,
        )
    )


@router.guest_message(F.text.regexp(_REFADD_GUEST_FILTER))
async def handle_guest_reference_add(
    message: Message,
    database: Database,
    bot_username: str,
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
        await _save_context_reference(
            message=message,
            character_name=character_name,
            database=database,
            audit_logger=audit_logger,
        ),
    )


@router.message(Command("refdel"))
async def handle_reference_delete_command(
    message: Message,
    command: CommandObject,
    database: Database,
    audit_logger: TelegramAuditLogger,
) -> None:
    if not command.args:
        await message.answer(
            "Укажите персонажа и номер референса.\n\n"
            "Пример: <code>/refdel Аид 2</code>"
        )
        return
    try:
        result = await delete_reference_by_index(database, command.args)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    if result.reference is None:
        await message.answer("Референс уже удалён.")
        return
    caller = get_caller_user(message)
    await audit_logger.send(
        "Референс персонажа удалён",
        level="WARNING",
        character=result.character.name,
        reference_id=result.reference.id,
        remaining=result.remaining,
        deleted_by=caller.id if caller else None,
    )
    await message.answer(
        f"🗑 Референс <b>{result.index}</b> персонажа "
        f"<b>{escape(result.character.name)}</b> удалён. "
        f"Осталось: <b>{result.remaining}</b>."
    )


async def _edit_reference_page(
    callback: CallbackQuery,
    bot: Bot,
    page: ReferencePage,
) -> None:
    if page.reference is None:
        raise RuntimeError("Референс не найден.")
    media = InputMediaPhoto(
        media=page.reference.telegram_file_id,
        caption=format_reference_caption(page),
        parse_mode=ParseMode.HTML,
    )
    keyboard = build_reference_keyboard(page)
    if callback.inline_message_id:
        await bot.edit_message_media(
            inline_message_id=callback.inline_message_id,
            media=media,
            reply_markup=keyboard,
        )
    elif isinstance(callback.message, Message):
        await callback.message.edit_media(media=media, reply_markup=keyboard)
    else:
        raise RuntimeError("Сообщение больше недоступно.")


async def _edit_reference_keyboard(
    callback: CallbackQuery,
    bot: Bot,
    page: ReferencePage,
    *,
    confirm_delete: bool,
) -> None:
    keyboard = (
        build_reference_delete_keyboard(page)
        if confirm_delete
        else build_reference_keyboard(page)
    )
    if callback.inline_message_id:
        await bot.edit_message_reply_markup(
            inline_message_id=callback.inline_message_id,
            reply_markup=keyboard,
        )
    elif isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    else:
        raise RuntimeError("Сообщение больше недоступно.")


async def _show_empty_reference_state(
    callback: CallbackQuery,
    bot: Bot,
    character_name: str,
) -> None:
    caption = (
        f"<b>{escape(character_name)}</b>\n\n"
        "Референс удалён. У персонажа больше нет референсов."
    )
    if callback.inline_message_id:
        await bot.edit_message_caption(
            inline_message_id=callback.inline_message_id,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=None,
        )
        return
    if isinstance(callback.message, Message):
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            await callback.message.edit_caption(
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=None,
            )
        return
    raise RuntimeError("Сообщение больше недоступно.")


@router.callback_query(
    ReferenceCallback.filter(F.action.in_({"delete_prompt", "cancel_delete", "delete"}))
)
async def handle_reference_delete_callback(
    callback: CallbackQuery,
    callback_data: ReferenceCallback,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
) -> None:
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
    try:
        if callback_data.action in {"delete_prompt", "cancel_delete"}:
            if page.reference.id != callback_data.reference_id:
                await callback.answer(
                    "Список изменился. Откройте референсы заново.",
                    show_alert=True,
                )
                return
            await _edit_reference_keyboard(
                callback,
                bot,
                page,
                confirm_delete=callback_data.action == "delete_prompt",
            )
            await callback.answer()
            return
        result = await delete_character_reference(
            database,
            callback_data.character_id,
            callback_data.reference_id,
        )
        if result.reference is None:
            await callback.answer("Референс уже удалён.", show_alert=True)
            return
        await audit_logger.send(
            "Референс персонажа удалён",
            level="WARNING",
            character=page.character.name,
            reference_id=result.reference.id,
            remaining=result.total,
            deleted_by=callback.from_user.id,
        )
        if result.total == 0:
            await _show_empty_reference_state(callback, bot, page.character.name)
        else:
            next_page = await get_reference_page(
                database,
                callback_data.character_id,
                min(callback_data.offset, result.total - 1),
            )
            if next_page is None or next_page.reference is None:
                raise RuntimeError("Не удалось загрузить следующий референс.")
            await _edit_reference_page(callback, bot, next_page)
    except (TelegramBadRequest, RuntimeError) as error:
        logger.info("Reference deletion UI failed: %s", error)
        await callback.answer("Не удалось обновить референс.", show_alert=True)
        return
    await callback.answer("Референс удалён.")

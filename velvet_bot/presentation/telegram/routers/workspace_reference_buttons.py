from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from velvet_bot.access import get_caller_user
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.character_resolution import load_character_by_id
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.reference_access import require_reference_workspace_access
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.routers.workspace_owner_controls import (
    WorkspaceReferenceEntryCallback,
    _load_reference_characters,
    _reference_dashboard_keyboard,
    _require_personal_module,
)
from velvet_bot.presentation.telegram.routers.workspace_reference_library import (
    PersonalReferenceContext,
    PersonalReferenceWorkspaceFilter,
    _reject_access,
)
from velvet_bot.reference_catalog import (
    delete_character_reference,
    get_reference_page,
    replace_character_reference,
)
from velvet_bot.reference_media import (
    extract_reference_source,
    prepare_reference_source,
    validate_reference_document,
)
from velvet_bot.reference_ui import ReferenceCallback, format_reference_caption
from velvet_bot.reference_uploads import ReferenceUploadSession, ReferenceUploadSessions

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_MANAGE_ACTIONS = {
    "manage_show",
    "manage_add",
    "manage_replace",
    "manage_delete_prompt",
    "manage_delete_cancel",
    "manage_delete",
    "manage_compare",
    "manage_back",
    "manage_close",
    "manage_upload_done",
    "manage_upload_cancel",
}


def _callback(
    action: str,
    *,
    character_id: int,
    reference_id: int = 0,
    offset: int = 0,
) -> str:
    return ReferenceCallback(
        action=action,
        character_id=int(character_id),
        reference_id=int(reference_id),
        offset=max(0, int(offset)),
    ).pack()


def _reference_keyboard(page) -> InlineKeyboardMarkup:
    if page.reference is None or page.total <= 0:
        return _empty_reference_keyboard(page.character.id)
    common = {
        "character_id": page.character.id,
        "reference_id": page.reference.id,
    }
    if page.total == 1:
        rows: list[list[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(
                    text="1 / 1",
                    callback_data=_callback("manage_show", offset=0, **common),
                )
            ]
        ]
    else:
        rows = [
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=_callback(
                        "manage_show",
                        offset=(page.offset - 1) % page.total,
                        **common,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{page.offset + 1} / {page.total}",
                    callback_data=_callback(
                        "manage_show",
                        offset=page.offset,
                        **common,
                    ),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=_callback(
                        "manage_show",
                        offset=(page.offset + 1) % page.total,
                        **common,
                    ),
                ),
            ]
        ]
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="➕ Добавить референс",
                    callback_data=_callback(
                        "manage_add",
                        offset=page.offset,
                        **common,
                    ),
                ),
                InlineKeyboardButton(
                    text="🔄 Заменить этот",
                    callback_data=_callback(
                        "manage_replace",
                        offset=page.offset,
                        **common,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить референс",
                    callback_data=_callback(
                        "manage_delete_prompt",
                        offset=page.offset,
                        **common,
                    ),
                ),
                InlineKeyboardButton(
                    text="🔎 Сравнить результат",
                    callback_data=_callback(
                        "manage_compare",
                        offset=page.offset,
                        **common,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К персонажам",
                    callback_data=_callback(
                        "manage_back",
                        offset=page.offset,
                        **common,
                    ),
                ),
                InlineKeyboardButton(
                    text="✖ Закрыть",
                    callback_data=_callback(
                        "manage_close",
                        offset=page.offset,
                        **common,
                    ),
                ),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _empty_reference_keyboard(character_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить референсы",
                    callback_data=_callback(
                        "manage_add",
                        character_id=character_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К персонажам",
                    callback_data=_callback(
                        "manage_back",
                        character_id=character_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="✖ Закрыть",
                    callback_data=_callback(
                        "manage_close",
                        character_id=character_id,
                    ),
                ),
            ],
        ]
    )


def _delete_confirmation_keyboard(page) -> InlineKeyboardMarkup:
    assert page.reference is not None
    common = {
        "character_id": page.character.id,
        "reference_id": page.reference.id,
        "offset": page.offset,
    }
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, удалить",
                    callback_data=_callback("manage_delete", **common),
                ),
                InlineKeyboardButton(
                    text="↩️ Отмена",
                    callback_data=_callback("manage_delete_cancel", **common),
                ),
            ]
        ]
    )


def _upload_keyboard(
    *,
    character_id: int,
    reference_id: int = 0,
    offset: int = 0,
) -> InlineKeyboardMarkup:
    common = {
        "character_id": character_id,
        "reference_id": reference_id,
        "offset": offset,
    }
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Завершить",
                    callback_data=_callback("manage_upload_done", **common),
                ),
                InlineKeyboardButton(
                    text="✖ Отменить",
                    callback_data=_callback("manage_upload_cancel", **common),
                ),
            ]
        ]
    )


async def _send_reference_page(
    bot: Bot,
    *,
    chat_id: int,
    page,
) -> Message:
    if page.reference is None:
        raise ValueError("У персонажа пока нет референсов.")
    return await bot.send_photo(
        chat_id=chat_id,
        photo=page.reference.telegram_file_id,
        caption=format_reference_caption(page),
        parse_mode=ParseMode.HTML,
        reply_markup=_reference_keyboard(page),
        protect_content=True,
    )


async def _edit_reference_page(
    callback: CallbackQuery,
    *,
    page,
) -> None:
    if page.reference is None:
        await callback.answer("Референсы больше не найдены.", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Сообщение больше недоступно.", show_alert=True)
        return
    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=page.reference.telegram_file_id,
                caption=format_reference_caption(page),
                parse_mode=ParseMode.HTML,
            ),
            reply_markup=_reference_keyboard(page),
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            await callback.message.answer_photo(
                photo=page.reference.telegram_file_id,
                caption=format_reference_caption(page),
                parse_mode=ParseMode.HTML,
                reply_markup=_reference_keyboard(page),
                protect_content=True,
            )
    await callback.answer()


class PendingReferenceReplaceFilter(BaseFilter):
    async def __call__(
        self,
        message: Message,
        reference_uploads: ReferenceUploadSessions,
    ) -> dict[str, ReferenceUploadSession] | bool:
        caller = get_caller_user(message)
        if caller is None:
            return False
        session = reference_uploads.get(caller.id)
        if session is None or session.replace_reference_id is None:
            return False
        return {"reference_replace_session": session}


@router.callback_query(
    WorkspaceReferenceEntryCallback.filter(F.action == "open")
)
async def handle_reference_character_open(
    callback: CallbackQuery,
    callback_data: WorkspaceReferenceEntryCallback,
    database: Database,
    bot: Bot,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    try:
        workspace = await _require_personal_module(
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
            user_id=callback.from_user.id,
            workspace_id=callback_data.workspace_id,
            module_key="references",
            minimum_role="viewer",
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    character = await load_character_by_id(
        database,
        character_id=callback_data.character_id,
        workspace_id=workspace.id,
    )
    if character is None:
        await callback.answer("Персонаж не найден в этом пространстве.", show_alert=True)
        return
    page = await get_reference_page(
        database,
        character.id,
        0,
        workspace_id=workspace.id,
    )
    if not isinstance(callback.message, Message):
        await callback.answer("Не удалось определить чат.", show_alert=True)
        return
    if page is None or page.reference is None:
        await callback.message.answer(
            f"<b>🧬 {escape(character.name)}</b>\n\n"
            "У персонажа пока нет референсов. Добавьте один или несколько файлов "
            "кнопкой ниже.",
            reply_markup=_empty_reference_keyboard(character.id),
        )
        await callback.answer()
        return
    try:
        await _send_reference_page(
            bot,
            chat_id=callback.message.chat.id,
            page=page,
        )
    except TelegramAPIError:
        await callback.answer("Telegram не смог открыть референс.", show_alert=True)
        return
    await callback.answer()


@router.callback_query(
    ReferenceCallback.filter(F.action.in_(_MANAGE_ACTIONS)),
    PersonalReferenceWorkspaceFilter("viewer"),
)
async def handle_reference_manage(
    callback: CallbackQuery,
    callback_data: ReferenceCallback,
    personal_reference_context: PersonalReferenceContext,
    database: Database,
    bot: Bot,
    workspace_service: WorkspaceService,
    reference_uploads: ReferenceUploadSessions,
    audit_logger: TelegramAuditLogger,
) -> None:
    if await _reject_access(callback, personal_reference_context):
        return
    action = callback_data.action
    if action == "manage_close":
        if isinstance(callback.message, Message):
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
        await callback.answer()
        return
    if action in {"manage_upload_done", "manage_upload_cancel"}:
        stopped = reference_uploads.stop(callback.from_user.id)
        if stopped is None:
            await callback.answer("Активной загрузки референсов нет.", show_alert=True)
            return
        text = (
            "Загрузка референсов завершена."
            if action == "manage_upload_done"
            else "Загрузка референсов отменена. Уже сохранённые файлы не удалены."
        )
        await callback.answer(text, show_alert=True)
        return
    if action == "manage_back":
        rows = await _load_reference_characters(
            database,
            workspace_id=personal_reference_context.workspace_id,
        )
        if isinstance(callback.message, Message):
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
            await callback.message.answer(
                "<b>🧬 Референсы</b>\n\n"
                f"Персонажей: <b>{len(rows)}</b>\n\n"
                "Выберите персонажа, чтобы открыть его библиотеку референсов.",
                reply_markup=_reference_dashboard_keyboard(
                    workspace_id=personal_reference_context.workspace_id,
                    rows=rows,
                ),
            )
        await callback.answer()
        return

    page = await get_reference_page(
        database,
        callback_data.character_id,
        callback_data.offset,
        workspace_id=personal_reference_context.workspace_id,
    )
    if page is None:
        await callback.answer("Персонаж не найден в активном пространстве.", show_alert=True)
        return
    if action == "manage_add":
        try:
            await require_reference_workspace_access(
                database,
                workspace_service,
                workspace_id=personal_reference_context.workspace_id,
                user_id=callback.from_user.id,
                minimum_role="editor",
            )
        except WorkspaceAccessError as error:
            await callback.answer(str(error), show_alert=True)
            return
        reference_uploads.start(
            callback.from_user.id,
            character_id=page.character.id,
            character_name=page.character.name,
            workspace_id=personal_reference_context.workspace_id,
        )
        if isinstance(callback.message, Message):
            await callback.message.answer(
                f"<b>Добавление референсов · {escape(page.character.name)}</b>\n\n"
                "Отправляйте фотографии или изображения-документы JPG, PNG и WEBP. "
                "Можно прислать несколько файлов подряд, затем нажать «Завершить».",
                reply_markup=_upload_keyboard(character_id=page.character.id),
            )
        await callback.answer()
        return
    if page.reference is None:
        await callback.answer("У персонажа пока нет референсов.", show_alert=True)
        return
    if action == "manage_show":
        await _edit_reference_page(callback, page=page)
        return
    if action == "manage_compare":
        await callback.answer(
            f"Ответьте на готовое изображение командой /compare_ref "
            f"{page.character.name} {page.offset + 1}",
            show_alert=True,
        )
        return

    try:
        await require_reference_workspace_access(
            database,
            workspace_service,
            workspace_id=personal_reference_context.workspace_id,
            user_id=callback.from_user.id,
            minimum_role="editor",
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    if page.reference.id != callback_data.reference_id:
        await callback.answer(
            "Список изменился. Откройте референсы заново.",
            show_alert=True,
        )
        return
    if action == "manage_replace":
        reference_uploads.start(
            callback.from_user.id,
            character_id=page.character.id,
            character_name=page.character.name,
            workspace_id=personal_reference_context.workspace_id,
            replace_reference_id=page.reference.id,
            replace_offset=page.offset,
        )
        if isinstance(callback.message, Message):
            await callback.message.answer(
                f"<b>Замена референса {page.offset + 1} · "
                f"{escape(page.character.name)}</b>\n\n"
                "Отправьте одно новое изображение. Старый референс будет заменён "
                "только после успешного сохранения нового файла.",
                reply_markup=_upload_keyboard(
                    character_id=page.character.id,
                    reference_id=page.reference.id,
                    offset=page.offset,
                ),
            )
        await callback.answer()
        return
    if action == "manage_delete_prompt":
        if isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(
                reply_markup=_delete_confirmation_keyboard(page)
            )
        await callback.answer()
        return
    if action == "manage_delete_cancel":
        if isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(
                reply_markup=_reference_keyboard(page)
            )
        await callback.answer()
        return
    if action == "manage_delete":
        result = await delete_character_reference(
            database,
            page.character.id,
            page.reference.id,
            workspace_id=personal_reference_context.workspace_id,
        )
        if result.reference is None:
            await callback.answer("Референс уже удалён.", show_alert=True)
            return
        await audit_logger.send(
            "Референс личного пространства удалён кнопкой",
            level="WARNING",
            workspace_id=personal_reference_context.workspace_id,
            character=page.character.name,
            reference_id=result.reference.id,
            remaining=result.total,
            deleted_by=callback.from_user.id,
        )
        if result.total == 0:
            if isinstance(callback.message, Message):
                try:
                    await callback.message.delete()
                except TelegramBadRequest:
                    pass
                await callback.message.answer(
                    f"<b>🧬 {escape(page.character.name)}</b>\n\n"
                    "Последний референс удалён.",
                    reply_markup=_empty_reference_keyboard(page.character.id),
                )
            await callback.answer("Референс удалён.")
            return
        next_page = await get_reference_page(
            database,
            page.character.id,
            min(page.offset, result.total - 1),
            workspace_id=personal_reference_context.workspace_id,
        )
        if next_page is None or next_page.reference is None:
            await callback.answer("Не удалось открыть следующий референс.", show_alert=True)
            return
        await _edit_reference_page(callback, page=next_page)
        return
    await callback.answer("Неизвестное действие.", show_alert=True)


@router.message(
    F.photo | F.document,
    F.chat.type == ChatType.PRIVATE,
    PendingReferenceReplaceFilter(),
)
async def handle_reference_replacement_upload(
    message: Message,
    reference_replace_session: ReferenceUploadSession,
    reference_uploads: ReferenceUploadSessions,
    database: Database,
    bot: Bot,
    workspace_service: WorkspaceService,
    audit_logger: TelegramAuditLogger,
) -> None:
    caller = get_caller_user(message)
    if caller is None:
        return
    try:
        await require_reference_workspace_access(
            database,
            workspace_service,
            workspace_id=reference_replace_session.workspace_id,
            user_id=caller.id,
            minimum_role="editor",
        )
    except WorkspaceAccessError as error:
        reference_uploads.stop(caller.id)
        await message.answer(escape(str(error)))
        return
    source = extract_reference_source(message)
    if source is None:
        if message.document is not None:
            await message.answer(
                validate_reference_document(message.document)
                or "Документ нельзя использовать как референс."
            )
        return
    character = await load_character_by_id(
        database,
        character_id=reference_replace_session.character_id,
        workspace_id=reference_replace_session.workspace_id,
    )
    if character is None:
        reference_uploads.stop(caller.id)
        await message.answer("Персонаж удалён. Замена референса отменена.")
        return
    try:
        prepared = await prepare_reference_source(
            source,
            bot=bot,
            staging_chat_id=audit_logger.chat_id or message.chat.id,
        )
        reference = await replace_character_reference(
            database,
            character,
            reference_replace_session.replace_reference_id or 0,
            prepared,
            added_by=caller.id,
            workspace_id=reference_replace_session.workspace_id,
        )
    except (ValueError, RuntimeError) as error:
        await message.answer(escape(str(error)))
        return
    reference_uploads.stop(caller.id)
    await audit_logger.send(
        "Референс личного пространства заменён",
        level="SUCCESS",
        workspace_id=reference_replace_session.workspace_id,
        character=character.name,
        reference_id=reference.id,
        replaced_by=caller.id,
    )
    page = await get_reference_page(
        database,
        character.id,
        reference_replace_session.replace_offset,
        workspace_id=reference_replace_session.workspace_id,
    )
    await message.answer(
        f"✅ Референс <b>{reference_replace_session.replace_offset + 1}</b> "
        f"персонажа <b>{escape(character.name)}</b> заменён."
    )
    if page is not None and page.reference is not None:
        try:
            await _send_reference_page(bot, chat_id=message.chat.id, page=page)
        except TelegramAPIError:
            logger.exception("Failed to display replaced workspace reference")


__all__ = ("PendingReferenceReplaceFilter", "router")

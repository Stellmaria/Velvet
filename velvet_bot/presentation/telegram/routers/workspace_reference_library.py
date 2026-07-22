from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InputMediaPhoto,
    InputTextMessageContent,
    Message,
)

from velvet_bot.access import get_caller_user
from velvet_bot.application.owner_references import parse_reference_index
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.character_resolution import load_character_by_id, resolve_character
from velvet_bot.core.config import load_settings
from velvet_bot.database import Character, Database
from velvet_bot.domains.references import CharacterReference, ReferencePage
from velvet_bot.domains.references.comparison_repository import _save_report
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID, WorkspaceRole
from velvet_bot.domains.workspaces.reference_access import (
    require_reference_workspace_access,
    resolve_personal_reference_access,
)
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.local_ai_runtime import get_local_ai_lock
from velvet_bot.presentation.telegram.routers.references.albums import (
    send_reference_collection,
)
from velvet_bot.presentation.telegram.routers.references.comparison import (
    _download_file,
    _format_report,
    _result_file,
)
from velvet_bot.presentation.telegram.routers.references.parsing import (
    parse_reference_add_character,
    parse_reference_character,
    parse_reference_selector,
)
from velvet_bot.reference_catalog import (
    add_character_reference,
    delete_character_reference,
    get_reference_page,
    list_character_references,
)
from velvet_bot.reference_comparison import ReferenceComparisonClient
from velvet_bot.reference_media import (
    ReferenceSource,
    extract_reference_source,
    prepare_reference_source,
    validate_reference_document,
)
from velvet_bot.reference_ui import (
    ReferenceCallback,
    build_reference_delete_keyboard,
    build_reference_keyboard,
    format_reference_caption,
)
from velvet_bot.reference_uploads import ReferenceUploadSession, ReferenceUploadSessions
from velvet_bot.workspace_ui import WorkspaceCallback

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_REF_MENTION_FILTER = re.compile(
    r"^(?:"
    r"@[A-Za-z0-9_]+\s+/?refs?\s+.+|"
    r"/?refs?\s+@[A-Za-z0-9_]+\s+.+|"
    r"/?refs?\s+.+\s+@[A-Za-z0-9_]+"
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


@dataclass(frozen=True, slots=True)
class PersonalReferenceContext:
    workspace_id: int
    error: str | None = None


class PersonalReferenceWorkspaceFilter(BaseFilter):
    def __init__(
        self,
        minimum_role: WorkspaceRole,
        *,
        require_qwen: bool = False,
    ) -> None:
        self._minimum_role = minimum_role
        self._require_qwen = require_qwen

    async def __call__(
        self,
        event: Message | CallbackQuery | InlineQuery,
        database: Database,
        workspace_service: WorkspaceService,
    ) -> dict[str, PersonalReferenceContext] | bool:
        user_id = _event_user_id(event)
        if user_id is None:
            return False
        access = await resolve_personal_reference_access(
            database,
            workspace_service,
            user_id=user_id,
            minimum_role=self._minimum_role,
            require_qwen=self._require_qwen,
        )
        if access is None:
            return False
        return {
            "personal_reference_context": PersonalReferenceContext(
                workspace_id=access.workspace_id,
                error=access.error,
            )
        }


class PersonalReferenceSessionFilter(BaseFilter):
    def __init__(self, minimum_role: WorkspaceRole = "editor") -> None:
        self._minimum_role = minimum_role

    async def __call__(
        self,
        message: Message,
        database: Database,
        workspace_service: WorkspaceService,
        reference_uploads: ReferenceUploadSessions,
    ) -> dict[str, object] | bool:
        user_id = _event_user_id(message)
        if user_id is None:
            return False
        session = reference_uploads.get(user_id)
        if session is None or session.workspace_id == DEFAULT_WORKSPACE_ID:
            return False
        error: str | None = None
        try:
            await require_reference_workspace_access(
                database,
                workspace_service,
                workspace_id=session.workspace_id,
                user_id=user_id,
                minimum_role=self._minimum_role,
            )
        except WorkspaceAccessError as access_error:
            error = str(access_error)
        return {
            "personal_reference_context": PersonalReferenceContext(
                workspace_id=session.workspace_id,
                error=error,
            ),
            "personal_reference_session": session,
        }


def _event_user_id(event: Message | CallbackQuery | InlineQuery) -> int | None:
    if isinstance(event, Message):
        caller = get_caller_user(event)
        return caller.id if caller is not None else None
    return event.from_user.id if event.from_user is not None else None


async def _reject_access(
    event: Message | CallbackQuery | InlineQuery,
    context: PersonalReferenceContext,
) -> bool:
    if context.error is None:
        return False
    if isinstance(event, CallbackQuery):
        await event.answer(context.error, show_alert=True)
    elif isinstance(event, InlineQuery):
        await event.answer([], cache_time=1, is_personal=True)
    else:
        await event.answer(escape(context.error))
    return True


@router.callback_query(
    WorkspaceCallback.filter((F.action == "module") & (F.module_key == "qwen")),
    PersonalReferenceWorkspaceFilter("reviewer", require_qwen=True),
)
async def handle_workspace_qwen_entry(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    personal_reference_context: PersonalReferenceContext,
) -> None:
    """Expose only the tenant-safe Qwen reference workflow, never system jobs."""
    if await _reject_access(callback, personal_reference_context):
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    if callback_data.workspace_id != personal_reference_context.workspace_id:
        await callback.answer(
            "Кнопка относится к другому пространству. Откройте меню заново.",
            show_alert=True,
        )
        return
    text = (
        "<b>🤖 Qwen · личное пространство</b>\n\n"
        "Qwen сравнивает результат с референсами персонажа из этого пространства. "
        "Откройте библиотеку референсов, выберите персонажа и используйте сравнение "
        "на карточке референса.\n\n"
        "Системный Quality Center, общая AI-очередь и медиасеты Velvet Anatomy "
        "сюда не попадают."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧬 Открыть референсы",
                    callback_data=WorkspaceCallback(
                        action="module",
                        workspace_id=personal_reference_context.workspace_id,
                        module_key="references",
                    ).pack(),
                )
            ]
        ]
    )
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


async def _resolve_collection(
    database: Database,
    request: str,
    *,
    workspace_id: int,
) -> tuple[Character | None, list[CharacterReference], int | None]:
    cleaned = " ".join(request.split()).strip()
    if not cleaned:
        return None, [], None
    character = await resolve_character(
        database,
        cleaned,
        workspace_id=workspace_id,
    )
    if character is not None:
        references = await list_character_references(
            database,
            character.id,
            limit=50,
            workspace_id=workspace_id,
        )
        return character, references, None
    character_name, selected_index = parse_reference_selector(cleaned)
    if selected_index is None:
        return None, [], None
    character = await resolve_character(
        database,
        character_name,
        workspace_id=workspace_id,
    )
    if character is None:
        return None, [], selected_index
    references = await list_character_references(
        database,
        character.id,
        limit=50,
        workspace_id=workspace_id,
    )
    return character, references, selected_index


async def _store_reference(
    *,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    character: Character,
    source: ReferenceSource,
    workspace_id: int,
    added_by: int | None,
    staging_chat_id: int | None,
) -> tuple[bool, int]:
    prepared = await prepare_reference_source(
        source,
        bot=bot,
        staging_chat_id=staging_chat_id,
    )
    result = await add_character_reference(
        database,
        character,
        prepared,
        added_by=added_by,
        workspace_id=workspace_id,
    )
    if result.created:
        await audit_logger.send(
            "Референс личного пространства добавлен",
            level="SUCCESS",
            workspace_id=workspace_id,
            character=character.name,
            reference_id=result.reference.id,
            total=result.total,
            added_by=added_by,
        )
    return result.created, result.total


async def _start_or_add(
    message: Message,
    character_name: str,
    *,
    context: PersonalReferenceContext,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    reference_uploads: ReferenceUploadSessions,
) -> None:
    if await _reject_access(message, context):
        return
    user_id = _event_user_id(message)
    if user_id is None:
        await message.answer("Не удалось определить пользователя.")
        return
    character = await resolve_character(
        database,
        character_name,
        workspace_id=context.workspace_id,
    )
    if character is None:
        await message.answer("Такой персонаж не найден в выбранном пространстве.")
        return

    source_message = message.reply_to_message or message
    source = extract_reference_source(source_message)
    if source_message.document is not None and source is None:
        await message.answer(
            validate_reference_document(source_message.document)
            or "Документ нельзя использовать как референс."
        )
        return

    created = False
    total: int | None = None
    if source is not None:
        try:
            created, total = await _store_reference(
                database=database,
                bot=bot,
                audit_logger=audit_logger,
                character=character,
                source=source,
                workspace_id=context.workspace_id,
                added_by=user_id,
                staging_chat_id=audit_logger.chat_id or message.chat.id,
            )
        except (ValueError, RuntimeError) as error:
            await message.answer(escape(str(error)))
            return

    if message.chat.type == ChatType.PRIVATE:
        reference_uploads.start(
            user_id,
            character_id=character.id,
            character_name=character.name,
            workspace_id=context.workspace_id,
        )
        if created:
            reference_uploads.increment(user_id)
        status = (
            f"\nТекущий референс сохранён. Всего: <b>{total}</b>."
            if created and total is not None
            else (
                f"\nЭтот референс уже был сохранён. Всего: <b>{total}</b>."
                if source is not None and total is not None
                else ""
            )
        )
        await message.answer(
            f"<b>Личная библиотека: {escape(character.name)}</b>\n\n"
            "Пространство и персонаж зафиксированы для этой загрузки. "
            "Отправляйте фотографии или изображения-документы JPG, PNG и WEBP.\n\n"
            "Завершение: <code>/refdone</code> · отмена: <code>/refcancel</code>"
            f"{status}"
        )
        return

    if source is None:
        await message.answer(
            "Ответьте командой на фотографию или изображение-документ."
        )
        return
    await message.answer(
        (
            f"✅ Референс <b>{escape(character.name)}</b> добавлен. "
            f"Всего: <b>{total}</b>."
            if created
            else (
                f"Этот референс уже сохранён у <b>{escape(character.name)}</b>. "
                f"Всего: <b>{total}</b>."
            )
        )
    )


@router.message(
    Command("refadd"),
    PersonalReferenceWorkspaceFilter("editor"),
)
async def handle_workspace_reference_add(
    message: Message,
    command: CommandObject,
    personal_reference_context: PersonalReferenceContext,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    reference_uploads: ReferenceUploadSessions,
) -> None:
    if not command.args:
        await message.answer("Укажите персонажа: <code>/refadd Каэль</code>")
        return
    await _start_or_add(
        message,
        command.args,
        context=personal_reference_context,
        database=database,
        bot=bot,
        audit_logger=audit_logger,
        reference_uploads=reference_uploads,
    )


@router.message(
    F.text.regexp(_REFADD_MENTION_FILTER),
    PersonalReferenceWorkspaceFilter("editor"),
)
async def handle_workspace_reference_add_mention(
    message: Message,
    personal_reference_context: PersonalReferenceContext,
    database: Database,
    bot_username: str,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    reference_uploads: ReferenceUploadSessions,
) -> None:
    character_name = parse_reference_add_character(message.text or "", bot_username)
    if character_name is None:
        return
    await _start_or_add(
        message,
        character_name,
        context=personal_reference_context,
        database=database,
        bot=bot,
        audit_logger=audit_logger,
        reference_uploads=reference_uploads,
    )


@router.message(Command("refdone", "refcancel"), PersonalReferenceSessionFilter("viewer"))
async def handle_workspace_reference_upload_finish(
    message: Message,
    personal_reference_session: ReferenceUploadSession,
    reference_uploads: ReferenceUploadSessions,
) -> None:
    user_id = _event_user_id(message)
    if user_id is None:
        return
    stopped = reference_uploads.stop(user_id)
    if stopped is None:
        await message.answer("Активной загрузки референсов нет.")
        return
    await message.answer(
        "<b>Загрузка референсов завершена</b>\n\n"
        f"Персонаж: <b>{escape(personal_reference_session.character_name)}</b>\n"
        f"Добавлено за сеанс: <b>{personal_reference_session.added_count}</b>"
    )


@router.message(
    F.photo | F.document,
    F.chat.type == ChatType.PRIVATE,
    PersonalReferenceSessionFilter("editor"),
)
async def handle_workspace_reference_upload(
    message: Message,
    personal_reference_context: PersonalReferenceContext,
    personal_reference_session: ReferenceUploadSession,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    reference_uploads: ReferenceUploadSessions,
) -> None:
    user_id = _event_user_id(message)
    if user_id is None:
        return
    if await _reject_access(message, personal_reference_context):
        reference_uploads.stop(user_id)
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
        character_id=personal_reference_session.character_id,
        workspace_id=personal_reference_session.workspace_id,
    )
    if character is None:
        reference_uploads.stop(user_id)
        await message.answer("Персонаж удалён из этого пространства. Загрузка остановлена.")
        return
    try:
        created, total = await _store_reference(
            database=database,
            bot=bot,
            audit_logger=audit_logger,
            character=character,
            source=source,
            workspace_id=personal_reference_session.workspace_id,
            added_by=user_id,
            staging_chat_id=audit_logger.chat_id or message.chat.id,
        )
    except (ValueError, RuntimeError) as error:
        await message.answer(escape(str(error)))
        return
    if created:
        reference_uploads.increment(user_id)
    if message.media_group_id is None:
        await message.answer(
            f"✅ Референс добавлен. Всего у персонажа: <b>{total}</b>."
            if created
            else "Этот референс уже был добавлен."
        )


async def _show_collection(
    message: Message,
    request: str,
    *,
    context: PersonalReferenceContext,
    database: Database,
    bot: Bot,
) -> None:
    if await _reject_access(message, context):
        return
    character, references, selected_index = await _resolve_collection(
        database,
        request,
        workspace_id=context.workspace_id,
    )
    if character is None:
        await message.answer("Такой персонаж не найден в выбранном пространстве.")
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
            f"<b>{len(references)}</b> референс(а/ов)."
        )


@router.message(
    Command("refs", "ref"),
    PersonalReferenceWorkspaceFilter("viewer"),
)
async def handle_workspace_references(
    message: Message,
    command: CommandObject,
    personal_reference_context: PersonalReferenceContext,
    database: Database,
    bot: Bot,
) -> None:
    if not command.args:
        await message.answer("Укажите персонажа: <code>/ref Каэль</code>")
        return
    await _show_collection(
        message,
        command.args,
        context=personal_reference_context,
        database=database,
        bot=bot,
    )


@router.message(
    F.text.regexp(_REF_MENTION_FILTER),
    PersonalReferenceWorkspaceFilter("viewer"),
)
async def handle_workspace_reference_mention(
    message: Message,
    personal_reference_context: PersonalReferenceContext,
    database: Database,
    bot_username: str,
    bot: Bot,
) -> None:
    request = parse_reference_character(message.text or "", bot_username)
    if request is None:
        return
    await _show_collection(
        message,
        request,
        context=personal_reference_context,
        database=database,
        bot=bot,
    )


@router.message(
    Command("refdel"),
    PersonalReferenceWorkspaceFilter("editor"),
)
async def handle_workspace_reference_delete(
    message: Message,
    command: CommandObject,
    personal_reference_context: PersonalReferenceContext,
    database: Database,
    audit_logger: TelegramAuditLogger,
) -> None:
    if await _reject_access(message, personal_reference_context):
        return
    if not command.args:
        await message.answer("Пример: <code>/refdel Каэль 2</code>")
        return
    try:
        character_name, index = parse_reference_index(command.args)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    character = await resolve_character(
        database,
        character_name,
        workspace_id=personal_reference_context.workspace_id,
    )
    if character is None:
        await message.answer("Такой персонаж не найден в выбранном пространстве.")
        return
    page = await get_reference_page(
        database,
        character.id,
        index - 1,
        workspace_id=personal_reference_context.workspace_id,
    )
    if page is None or page.reference is None or index > page.total:
        await message.answer("Референс с таким номером не найден.")
        return
    result = await delete_character_reference(
        database,
        character.id,
        page.reference.id,
        workspace_id=personal_reference_context.workspace_id,
    )
    if result.reference is None:
        await message.answer("Референс уже удалён.")
        return
    await audit_logger.send(
        "Референс личного пространства удалён",
        level="WARNING",
        workspace_id=personal_reference_context.workspace_id,
        character=character.name,
        reference_id=result.reference.id,
        remaining=result.total,
        deleted_by=_event_user_id(message),
    )
    await message.answer(
        f"🗑 Референс <b>{index}</b> персонажа "
        f"<b>{escape(character.name)}</b> удалён. Осталось: <b>{result.total}</b>."
    )


@router.callback_query(
    ReferenceCallback.filter(),
    PersonalReferenceWorkspaceFilter("viewer"),
)
async def handle_workspace_reference_callback(
    callback: CallbackQuery,
    callback_data: ReferenceCallback,
    personal_reference_context: PersonalReferenceContext,
    database: Database,
    bot: Bot,
    workspace_service: WorkspaceService,
    audit_logger: TelegramAuditLogger,
) -> None:
    await _handle_workspace_reference_callback(
        callback,
        callback_data,
        personal_reference_context,
        database,
        bot,
        workspace_service,
        audit_logger,
    )


async def _handle_workspace_reference_callback(
    callback: CallbackQuery,
    callback_data: ReferenceCallback,
    personal_reference_context: PersonalReferenceContext,
    database: Database,
    bot: Bot,
    workspace_service: WorkspaceService,
    audit_logger: TelegramAuditLogger,
) -> None:
    if await _reject_access(callback, personal_reference_context):
        return
    page = await get_reference_page(
        database,
        callback_data.character_id,
        callback_data.offset,
        workspace_id=personal_reference_context.workspace_id,
    )
    if page is None:
        await callback.answer(
            "Персонаж не найден в активном пространстве.",
            show_alert=True,
        )
        return
    if page.reference is None:
        await callback.answer("Референсы больше не найдены.", show_alert=True)
        return
    if callback_data.action == "noop":
        await callback.answer()
        return
    if callback_data.action == "compare_help":
        await callback.answer(
            f"Ответьте на результат командой /compare_ref {page.character.name} "
            f"{page.offset + 1}",
            show_alert=True,
        )
        return
    if callback_data.action in {"delete_prompt", "cancel_delete", "delete"}:
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
        if callback_data.action in {"delete_prompt", "cancel_delete"}:
            keyboard = (
                build_reference_delete_keyboard(page)
                if callback_data.action == "delete_prompt"
                else build_reference_keyboard(page)
            )
            if callback.inline_message_id:
                await bot.edit_message_reply_markup(
                    inline_message_id=callback.inline_message_id,
                    reply_markup=keyboard,
                )
            elif isinstance(callback.message, Message):
                await callback.message.edit_reply_markup(reply_markup=keyboard)
            await callback.answer()
            return
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
            "Референс личного пространства удалён",
            level="WARNING",
            workspace_id=personal_reference_context.workspace_id,
            character=page.character.name,
            reference_id=result.reference.id,
            remaining=result.total,
            deleted_by=callback.from_user.id,
        )
        if result.total == 0:
            if isinstance(callback.message, Message):
                await callback.message.delete()
            else:
                await bot.edit_message_caption(
                    inline_message_id=callback.inline_message_id,
                    caption=(
                        f"<b>{escape(page.character.name)}</b>\n\n"
                        "У персонажа больше нет референсов."
                    ),
                    parse_mode=ParseMode.HTML,
                    reply_markup=None,
                )
            await callback.answer("Референс удалён.")
            return
        page = await get_reference_page(
            database,
            page.character.id,
            min(page.offset, result.total - 1),
            workspace_id=personal_reference_context.workspace_id,
        )
        if page is None or page.reference is None:
            await callback.answer("Не удалось открыть следующий референс.", show_alert=True)
            return

    media = InputMediaPhoto(
        media=page.reference.telegram_file_id,
        caption=format_reference_caption(page),
        parse_mode=ParseMode.HTML,
    )
    try:
        if callback.inline_message_id:
            await bot.edit_message_media(
                inline_message_id=callback.inline_message_id,
                media=media,
                reply_markup=build_reference_keyboard(page),
            )
        elif isinstance(callback.message, Message):
            await callback.message.edit_media(
                media=media,
                reply_markup=build_reference_keyboard(page),
            )
        else:
            await callback.answer("Сообщение больше недоступно.", show_alert=True)
            return
    except TelegramBadRequest as error:
        logger.info("Workspace reference media edit failed: %s", error)
        await callback.answer("Не удалось переключить референс.", show_alert=True)
        return
    await callback.answer()


@router.inline_query(
    F.query.regexp(r"^\s*/?refs?\s+.+$", flags=re.IGNORECASE),
    PersonalReferenceWorkspaceFilter("viewer"),
)
async def handle_workspace_inline_references(
    query: InlineQuery,
    personal_reference_context: PersonalReferenceContext,
    database: Database,
    bot_username: str,
) -> None:
    if await _reject_access(query, personal_reference_context):
        return
    request = parse_reference_character(query.query, bot_username)
    if request is None:
        await query.answer([], cache_time=1, is_personal=True)
        return
    character, references, selected_index = await _resolve_collection(
        database,
        request,
        workspace_id=personal_reference_context.workspace_id,
    )
    if character is None or not references:
        await query.answer([], cache_time=1, is_personal=True)
        return
    indexes = (
        [selected_index]
        if selected_index is not None and 1 <= selected_index <= len(references)
        else list(range(1, len(references) + 1))
    )
    results = []
    for index in indexes:
        page = ReferencePage(
            character=character,
            reference=references[index - 1],
            offset=index - 1,
            total=len(references),
        )
        results.append(
            InlineQueryResultCachedPhoto(
                id=f"wref-{personal_reference_context.workspace_id}-{page.reference.id}",
                photo_file_id=page.reference.telegram_file_id,
                caption=format_reference_caption(page),
                parse_mode=ParseMode.HTML,
                reply_markup=build_reference_keyboard(page),
            )
        )
    await query.answer(results[:50], cache_time=1, is_personal=True)


@router.guest_message(
    F.text.regexp(_REF_MENTION_FILTER),
    PersonalReferenceWorkspaceFilter("viewer"),
)
async def block_workspace_guest_reference_leak(
    message: Message,
    personal_reference_context: PersonalReferenceContext,
) -> None:
    if not message.guest_query_id:
        return
    result_id = hashlib.sha256(
        f"workspace-reference-private:{message.guest_query_id}".encode("utf-8")
    ).hexdigest()[:32]
    await message.answer_guest_query(
        InlineQueryResultArticle(
            id=result_id,
            title="Личная библиотека референсов",
            input_message_content=InputTextMessageContent(
                message_text=(
                    "Личные референсы доступны только владельцу и участникам "
                    "выбранного пространства в чате с ботом."
                ),
                parse_mode=ParseMode.HTML,
            ),
        )
    )


@router.message(
    Command("compare_ref", "compare_reference"),
    PersonalReferenceWorkspaceFilter("reviewer", require_qwen=True),
)
async def handle_workspace_reference_comparison(
    message: Message,
    command: CommandObject,
    personal_reference_context: PersonalReferenceContext,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger | None = None,
) -> None:
    if await _reject_access(message, personal_reference_context):
        return
    if message.chat.type != ChatType.PRIVATE:
        await message.answer("Сравнение внешности доступно в личном чате с ботом.")
        return
    if not command.args:
        await message.answer(
            "Ответьте командой на готовое изображение.\n\n"
            "Пример: <code>/compare_ref Каэль 2</code>"
        )
        return
    result_file = _result_file(message)
    if result_file is None:
        await message.answer(
            "Команду нужно отправить ответом на фотографию или изображение-документ."
        )
        return
    character, references, selected_index = await _resolve_collection(
        database,
        command.args,
        workspace_id=personal_reference_context.workspace_id,
    )
    if character is None:
        await message.answer("Такой персонаж не найден в выбранном пространстве.")
        return
    reference_index = selected_index or 1
    if not references:
        await message.answer(
            f"У персонажа <b>{escape(character.name)}</b> пока нет референсов."
        )
        return
    if reference_index < 1 or reference_index > len(references):
        await message.answer(
            f"У персонажа <b>{escape(character.name)}</b> только "
            f"<b>{len(references)}</b> референс(а/ов)."
        )
        return
    reference = references[reference_index - 1]
    settings = load_settings()
    if not settings.ai_vision_enabled:
        await message.answer("Локальный Qwen сейчас отключён в настройках бота.")
        return
    status = await message.answer(
        f"🔎 Сравниваю результат с референсом <b>{reference_index}</b> "
        f"персонажа <b>{escape(character.name)}</b>…"
    )
    result_file_id, result_unique_id = result_file
    try:
        reference_bytes, result_bytes = await asyncio.gather(
            _download_file(bot, reference.telegram_file_id),
            _download_file(bot, result_file_id),
        )
        client = ReferenceComparisonClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=settings.ai_vision_model,
            api_key=settings.ai_vision_api_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        async with get_local_ai_lock():
            report = await client.compare(reference_bytes, result_bytes)
        report_id = await _save_report(
            database,
            workspace_id=personal_reference_context.workspace_id,
            character_id=character.id,
            reference_id=reference.id,
            result_file_id=result_file_id,
            result_file_unique_id=result_unique_id,
            provider=client.provider,
            model=client.model,
            report=report,
            created_by=_event_user_id(message),
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:  # p2-approved-boundary: report-workspace-reference-comparison
        logger.exception(
            "Workspace reference comparison failed workspace_id=%s character_id=%s reference_id=%s",
            personal_reference_context.workspace_id,
            character.id,
            reference.id,
        )
        if audit_logger is not None:
            await audit_logger.error(
                "Ошибка сравнения с референсом личного пространства",
                error,
                workspace_id=personal_reference_context.workspace_id,
                character_id=character.id,
                reference_id=reference.id,
                result_file_id=result_file_id,
                user_id=_event_user_id(message),
            )
        await status.edit_text(
            "❌ Сравнение не завершено. Ошибка отправлена в центр инцидентов.\n\n"
            f"<code>{escape(str(error))[:900]}</code>"
        )
        return
    await status.edit_text(
        _format_report(
            report_id=report_id,
            character=character,
            reference_index=reference_index,
            reference_total=len(references),
            report=report,
        )
    )


__all__ = (
    "PersonalReferenceSessionFilter",
    "PersonalReferenceWorkspaceFilter",
    "router",
)

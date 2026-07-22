from __future__ import annotations

import logging
import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.app.save_sessions import SaveUploadSession, SaveUploadSessions
from velvet_bot.archive_topic_links import list_characters_by_archive_topic
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.character_resolution import load_character_by_id, resolve_character
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.media import MediaDescriptor, extract_media
from velvet_bot.media_preview_persistence import set_media_preview
from velvet_bot.presentation.telegram.routers.archive.parsing import (
    parse_guest_save_character,
)
from velvet_bot.presentation.telegram.routers.workspace_guided_ui import (
    guided_workspace_callback,
)
from velvet_bot.services.media_save import save_media_from_message

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_MENTION_SAVE_FILTER = re.compile(
    r"^(?:"
    r"@[A-Za-z0-9_]+\s+/?save\s+.+|"
    r"/?save\s+@[A-Za-z0-9_]+\s+.+|"
    r"/?save\s+.+\s+@[A-Za-z0-9_]+"
    r")$",
    re.IGNORECASE,
)


def _caller_user_id(message: Message) -> int | None:
    caller = message.from_user or message.guest_bot_caller_user
    return caller.id if caller else None


def _workspace_audit_fields(workspace_id: int) -> dict[str, int]:
    target = int(workspace_id)
    return {} if target == DEFAULT_WORKSPACE_ID else {"workspace_id": target}


class PendingSaveUploadFilter(BaseFilter):
    async def __call__(
        self,
        message: Message,
        save_upload_sessions: SaveUploadSessions,
    ) -> dict[str, SaveUploadSession] | bool:
        user_id = _caller_user_id(message)
        if user_id is None:
            return False
        session = save_upload_sessions.get(chat_id=message.chat.id, user_id=user_id)
        if session is None:
            return False
        return {"save_upload_session": session}


async def _persist_descriptor_preview(
    database: Database,
    *,
    media_id: int,
    media: MediaDescriptor,
) -> None:
    """Compatibility facade used by regression tests and legacy callers."""
    if not media.preview_file_id:
        return
    await set_media_preview(
        database,
        media_id=media_id,
        file_id=media.preview_file_id,
        file_unique_id=media.preview_file_unique_id,
        width=media.preview_width,
        height=media.preview_height,
        source=media.preview_source or "source_thumbnail",
    )


async def _archive_module_enabled(
    database: Database,
    *,
    workspace_id: int,
) -> bool:
    async with database.acquire() as connection:
        value = await connection.fetchval(
            """
            SELECT is_allowed AND is_enabled
            FROM workspace_modules
            WHERE workspace_id = $1::BIGINT
              AND module_key = 'archive'
            """,
            int(workspace_id),
        )
    return bool(value)


async def _require_workspace_save_access(
    database: Database,
    workspace_service: WorkspaceService,
    *,
    workspace_id: int,
    user_id: int,
) -> None:
    if int(workspace_id) == DEFAULT_WORKSPACE_ID:
        return
    global_owner = int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID
    await workspace_service.require_role(
        workspace_id=int(workspace_id),
        user_id=int(user_id),
        minimum_role="editor",
        global_owner=global_owner,
    )
    if not await _archive_module_enabled(database, workspace_id=workspace_id):
        raise WorkspaceAccessError("Модуль архива выключен или не разрешён Стэл.")


async def _resolve_save_workspace_id(
    database: Database,
    workspace_service: WorkspaceService,
    *,
    user_id: int,
) -> int:
    global_owner = int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID
    try:
        workspace = await workspace_service.resolve_active_workspace(
            user_id=int(user_id),
            global_owner=global_owner,
        )
    except WorkspaceAccessError:
        return DEFAULT_WORKSPACE_ID
    await _require_workspace_save_access(
        database,
        workspace_service,
        workspace_id=workspace.id,
        user_id=user_id,
    )
    return workspace.id


async def _build_save_response(
    message: Message,
    character_name: str,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    *,
    workspace_id: int,
) -> str:
    source_message = message.reply_to_message
    if source_message is None and extract_media(message) is not None:
        source_message = message
    if source_message is None:
        return (
            "Команда должна быть отправлена ответом на фото или видео.\n\n"
            "Нажмите «Ответить» на медиафайл и снова вызовите бота."
        )
    return await save_media_from_message(
        database,
        bot,
        audit_logger,
        request_message=message,
        source_message=source_message,
        character_name=character_name,
        actor_id=_caller_user_id(message),
        workspace_id=workspace_id,
    )


async def _handle_normal_save(
    message: Message,
    character_name: str,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    *,
    workspace_id: int,
) -> None:
    await message.answer(
        await _build_save_response(
            message,
            character_name,
            database,
            bot,
            audit_logger,
            workspace_id=workspace_id,
        )
    )


async def _start_save_session(
    message: Message,
    character_name: str,
    database: Database,
    save_upload_sessions: SaveUploadSessions,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> None:
    user_id = _caller_user_id(message)
    if user_id is None:
        await message.answer("Не удалось определить пользователя для режима сохранения.")
        return
    try:
        character = await resolve_character(
            database,
            character_name,
            workspace_id=workspace_id,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    if character is None:
        await message.answer(
            "Такой персонаж или быстрый тег не найден в выбранном пространстве. "
            "Сначала создайте его профиль в этом архиве."
        )
        return

    target_workspace_id = int(getattr(character, "workspace_id", workspace_id))
    save_upload_sessions.start(
        chat_id=message.chat.id,
        user_id=user_id,
        character_name=character.name,
        character_id=getattr(character, "id", None),
        workspace_id=target_workspace_id,
        command_message_id=message.message_id,
    )
    await message.answer(
        f"<b>Пакетная загрузка для {escape(character.name)}</b>\n\n"
        "Пространство зафиксировано для этой сессии. Теперь отправьте или "
        "перешлите фото, видео, анимации либо изображения/видео как файлы. "
        "Можно прислать альбом и затем продолжить следующими сообщениями — "
        "каждый поддерживаемый файл сохранится выбранному персонажу.\n\n"
        "После последнего файла нажмите «Закончить загрузку». Ниже также можно "
        "открыть карточку, выбрать другого персонажа или отменить режим — уже "
        "сохранённые файлы при отмене не удаляются. Сессия закроется через "
        "10 минут бездействия или по <code>/savecancel</code>.",
        reply_markup=_batch_save_keyboard(
            workspace_id=target_workspace_id,
            character_id=int(getattr(character, "id", 0) or 0),
        ),
    )


def _batch_save_keyboard(
    *,
    workspace_id: int,
    character_id: int,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="✅ Закончить загрузку",
                callback_data=guided_workspace_callback(
                    "savefinish",
                    workspace_id=workspace_id,
                    character_id=character_id,
                ),
            )
        ]
    ]
    if workspace_id != DEFAULT_WORKSPACE_ID:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text="↩️ Открыть карточку",
                        callback_data=guided_workspace_callback(
                            "saveopen",
                            workspace_id=workspace_id,
                            character_id=character_id,
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="👤 Другой персонаж",
                        callback_data=guided_workspace_callback(
                            "savepick",
                            workspace_id=workspace_id,
                        ),
                    )
                ],
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="✖ Отменить режим",
                callback_data=guided_workspace_callback(
                    "saveabort",
                    workspace_id=workspace_id,
                    character_id=character_id,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _has_context_media(message: Message) -> bool:
    return bool(
        (message.reply_to_message and extract_media(message.reply_to_message) is not None)
        or extract_media(message) is not None
    )


@router.message(Command("savecancel"))
async def handle_save_cancel(
    message: Message,
    save_upload_sessions: SaveUploadSessions,
) -> None:
    user_id = _caller_user_id(message)
    if user_id is None:
        await message.answer("Не удалось определить пользователя.")
        return
    stopped = save_upload_sessions.stop(chat_id=message.chat.id, user_id=user_id)
    if stopped is None:
        await message.answer("Активного ожидания файла нет.")
        return
    if stopped.saved_count:
        await message.answer(
            f"Загрузка для <b>{escape(stopped.character_name)}</b> завершена. "
            f"Обработано файлов: <b>{stopped.saved_count}</b>."
        )
    else:
        await message.answer(
            f"Загрузка для <b>{escape(stopped.character_name)}</b> отменена: "
            "файлы не были добавлены."
        )


@router.message(Command("save"))
async def handle_save_media(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    save_upload_sessions: SaveUploadSessions,
    workspace_service: WorkspaceService,
) -> None:
    if not command.args:
        await message.answer(
            "Укажите имя персонажа после команды.\n\n"
            "Вариант 1: ответьте на медиа командой <code>/save Аид</code>.\n"
            "Вариант 2: отправьте <code>/save Аид</code>, затем пришлите или "
            "перешлите файл."
        )
        return
    user_id = _caller_user_id(message)
    if user_id is None:
        await message.answer("Не удалось определить пользователя.")
        return
    try:
        workspace_id = await _resolve_save_workspace_id(
            database,
            workspace_service,
            user_id=user_id,
        )
    except WorkspaceAccessError as error:
        await message.answer(escape(str(error)))
        return
    if _has_context_media(message):
        await _handle_normal_save(
            message,
            command.args,
            database,
            bot,
            audit_logger,
            workspace_id=workspace_id,
        )
        return
    await _start_save_session(
        message,
        command.args,
        database,
        save_upload_sessions,
        workspace_id=workspace_id,
    )


@router.message(F.text.regexp(_MENTION_SAVE_FILTER))
async def handle_mention_save_media(
    message: Message,
    database: Database,
    bot_username: str,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    save_upload_sessions: SaveUploadSessions,
    workspace_service: WorkspaceService,
) -> None:
    character_name = parse_guest_save_character(message.text or "", bot_username)
    if character_name is None:
        return
    user_id = _caller_user_id(message)
    if user_id is None:
        await message.answer("Не удалось определить пользователя.")
        return
    try:
        workspace_id = await _resolve_save_workspace_id(
            database,
            workspace_service,
            user_id=user_id,
        )
    except WorkspaceAccessError as error:
        await message.answer(escape(str(error)))
        return
    if _has_context_media(message):
        await _handle_normal_save(
            message,
            character_name,
            database,
            bot,
            audit_logger,
            workspace_id=workspace_id,
        )
        return
    await _start_save_session(
        message,
        character_name,
        database,
        save_upload_sessions,
        workspace_id=workspace_id,
    )


@router.message(
    F.photo | F.video | F.animation | F.document,
    PendingSaveUploadFilter(),
)
async def handle_pending_save_upload(
    message: Message,
    save_upload_session: SaveUploadSession,
    save_upload_sessions: SaveUploadSessions,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    workspace_service: WorkspaceService | None = None,
) -> None:
    media = extract_media(message)
    if media is None:
        await message.answer(
            "Этот файл не поддерживается. Пришлите фото, видео, анимацию либо "
            "изображение/видео как документ. Ожидание остаётся активным."
        )
        return

    user_id = _caller_user_id(message)
    if user_id is None:
        await message.answer("Не удалось определить пользователя.")
        return
    if workspace_service is not None:
        try:
            await _require_workspace_save_access(
                database,
                workspace_service,
                workspace_id=save_upload_session.workspace_id,
                user_id=user_id,
            )
        except WorkspaceAccessError as error:
            save_upload_sessions.stop(chat_id=message.chat.id, user_id=user_id)
            await message.answer(escape(str(error)))
            return

    active = save_upload_sessions.get(chat_id=message.chat.id, user_id=user_id)
    if active is None:
        await message.answer(
            "Ожидание файла уже истекло. Повторите команду <code>/save Имя</code>."
        )
        return

    character = None
    if save_upload_session.character_id is not None:
        character = await load_character_by_id(
            database,
            character_id=save_upload_session.character_id,
            workspace_id=save_upload_session.workspace_id,
        )
        if character is None:
            await message.answer(
                "Персонаж был удалён из выбранного пространства. Сохранение отменено."
            )
            return

    save_kwargs = {
        "request_message": message,
        "source_message": message,
        "character_name": (
            character.name if character is not None else save_upload_session.character_name
        ),
        "actor_id": user_id,
        "workspace_id": save_upload_session.workspace_id,
    }
    if character is not None:
        save_kwargs["resolved_character"] = character

    result = await save_media_from_message(
            database,
            bot,
            audit_logger,
            **save_kwargs,
        )
    updated = save_upload_sessions.record_saved(
        chat_id=message.chat.id,
        user_id=user_id,
    )
    if updated is None:
        await message.answer(
            result
            + "\n\nСессия успела завершиться. Чтобы продолжить, снова выберите «Сохранить»."
        )
        return
    await message.answer(
        result
        + f"\n\n<b>Пакетная загрузка продолжается.</b> Обработано: "
        f"<b>{updated.saved_count}</b>. Пришлите следующий файл или завершите загрузку.",
        reply_markup=_batch_save_keyboard(
            workspace_id=updated.workspace_id,
            character_id=int(updated.character_id or 0),
        ),
    )


@router.message()
async def handle_new_archive_topic_media(
    message: Message,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
) -> None:
    if message.message_thread_id is None:
        return
    bot_info = await bot.get_me()
    if message.from_user and message.from_user.id == bot_info.id:
        return
    media = extract_media(message)
    if media is None:
        return
    characters = await list_characters_by_archive_topic(
        database,
        archive_chat_id=message.chat.id,
        archive_thread_id=message.message_thread_id,
    )
    if not characters:
        return

    for character in characters:
        workspace_id = int(getattr(character, "workspace_id", DEFAULT_WORKSPACE_ID))
        workspace_fields = _workspace_audit_fields(workspace_id)
        try:
            result = await database.save_character_media(
                character,
                media,
                saved_by=message.from_user.id if message.from_user else None,
                saved_in_chat=message.chat.id,
                source_chat_id=message.chat.id,
                source_message_id=message.message_id,
                source_thread_id=message.message_thread_id,
                command_message_id=None,
                archive_message_id=message.message_id,
            )
            await _persist_descriptor_preview(
                database,
                media_id=result.media_id,
                media=media,
            )
            logger.info(
                "Automatically archived topic media for workspace %s character %s from %s/%s",
                workspace_id,
                character.id,
                message.chat.id,
                message.message_thread_id,
            )
            if result.character_link_created:
                await audit_logger.send(
                    "Новое медиа принято из общей ветки",
                    level="SUCCESS",
                    character=character.name,
                    file=result.storage_file_name,
                    media_type=media.media_type,
                    archive_chat_id=message.chat.id,
                    archive_thread_id=message.message_thread_id,
                    archive_message_id=message.message_id,
                    linked_characters=len(characters),
                    **workspace_fields,
                )
        except Exception as error:  # p2-approved-boundary: report-topic-auto-archive-failure
            logger.exception(
                "Failed to automatically archive topic media for workspace %s character %s",
                workspace_id,
                character.id,
            )
            await audit_logger.error(
                "Ошибка автоматического архива общей ветки",
                error,
                character=character.name,
                archive_chat_id=message.chat.id,
                archive_thread_id=message.message_thread_id,
                archive_message_id=message.message_id,
                **workspace_fields,
            )


__all__ = (
    "PendingSaveUploadFilter",
    "handle_pending_save_upload",
    "handle_save_cancel",
    "handle_save_media",
    "parse_guest_save_character",
    "router",
)

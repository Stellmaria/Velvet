from __future__ import annotations

from html import escape
from typing import Any

from aiogram import Bot, Router
from aiogram.filters import BaseFilter
from aiogram.types import BotCommand, Message

from velvet_bot.app.save_sessions import (
    SaveUploadMode,
    SaveUploadSession,
    SaveUploadSessions,
)
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.character_resolution import load_character_by_id, resolve_character
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.media import extract_media
from velvet_bot.presentation.telegram.routers.archive import save as legacy_save
from velvet_bot.presentation.telegram.routers.core_operations_controllers import (
    workspace_product_experience,
)
from velvet_bot.services.media_save import save_media_from_message

router = Router(name=__name__)
_INSTALLED = False
_ORIGINAL_WORKSPACE_COMMANDS = workspace_product_experience._workspace_commands


class SaveModeCommandFilter(BaseFilter):
    """Route `/save` without media to one file and `/save_set` to a batch."""

    async def __call__(self, message: Message) -> dict[str, str] | bool:
        text = (message.text or message.caption or "").strip()
        if not text.startswith("/"):
            return False
        token, *tail = text.split(maxsplit=1)
        command = token[1:].split("@", maxsplit=1)[0].casefold()
        if command not in {"save", "save_set"}:
            return False
        if command == "save" and legacy_save._has_context_media(message):
            return False
        return {
            "save_mode": "single" if command == "save" else "set",
            "save_character_name": tail[0].strip() if tail else "",
        }


def _workspace_commands_with_save_modes(role: str) -> tuple[BotCommand, ...]:
    commands = list(_ORIGINAL_WORKSPACE_COMMANDS(role))
    if workspace_product_experience._ROLE_RANK.get(role, 0) < 30:
        return tuple(commands)

    result: list[BotCommand] = []
    inserted_set = False
    for command in commands:
        if command.command == "save":
            result.append(
                BotCommand(command="save", description="Сохранить один файл")
            )
            result.append(
                BotCommand(command="save_set", description="Пакетная загрузка файлов")
            )
            inserted_set = True
            continue
        result.append(command)
    if not inserted_set:
        result.append(BotCommand(command="save", description="Сохранить один файл"))
        result.append(
            BotCommand(command="save_set", description="Пакетная загрузка файлов")
        )
    return tuple(result)


def install_save_command_modes() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    workspace_product_experience._workspace_commands = _workspace_commands_with_save_modes


async def _start_save_mode_session(
    message: Message,
    *,
    character_name: str,
    mode: SaveUploadMode,
    database: Database,
    save_upload_sessions: SaveUploadSessions,
    workspace_service: WorkspaceService,
) -> None:
    command_name = "/save" if mode == "single" else "/save_set"
    if not character_name:
        await message.answer(
            f"Укажите имя персонажа после команды.\n\n"
            f"Пример: <code>{command_name} Аид</code>."
        )
        return

    user_id = legacy_save._caller_user_id(message)
    if user_id is None:
        await message.answer("Не удалось определить пользователя.")
        return
    try:
        workspace_id = await legacy_save._resolve_save_workspace_id(
            database,
            workspace_service,
            user_id=user_id,
        )
    except WorkspaceAccessError as error:
        await message.answer(escape(str(error)))
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
    character_id = int(getattr(character, "id", 0) or 0)
    save_upload_sessions.start(
        chat_id=message.chat.id,
        user_id=user_id,
        character_name=character.name,
        character_id=character_id or None,
        workspace_id=target_workspace_id,
        command_message_id=message.message_id,
        mode=mode,
    )

    if mode == "single":
        await message.answer(
            f"<b>Один файл для {escape(character.name)}</b>\n\n"
            "Отправьте или перешлите одно фото, видео, анимацию либо изображение/видео "
            "как документ. После первого поддерживаемого файла режим закроется сам.\n\n"
            "Чтобы отменить ожидание, используйте <code>/savecancel</code>."
        )
        return

    await message.answer(
        f"<b>Пакетная загрузка для {escape(character.name)}</b>\n\n"
        "Отправляйте или пересылайте фото, видео, анимации либо изображения/видео "
        "как документы. Можно прислать Telegram-альбом и затем продолжить следующими "
        "сообщениями: каждый поддерживаемый файл сохранится выбранному персонажу.\n\n"
        "После последнего файла нажмите «Закончить загрузку» или используйте "
        "<code>/savecancel</code>. Сессия закроется через 10 минут бездействия.",
        reply_markup=legacy_save._batch_save_keyboard(
            workspace_id=target_workspace_id,
            character_id=character_id,
        ),
    )


@router.message(SaveModeCommandFilter())
async def handle_save_mode_command(
    message: Message,
    save_mode: SaveUploadMode,
    save_character_name: str,
    database: Database,
    save_upload_sessions: SaveUploadSessions,
    workspace_service: WorkspaceService,
) -> None:
    await _start_save_mode_session(
        message,
        character_name=save_character_name,
        mode=save_mode,
        database=database,
        save_upload_sessions=save_upload_sessions,
        workspace_service=workspace_service,
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
        suffix = (
            "Ожидание одного файла остаётся активным."
            if save_upload_session.mode == "single"
            else "Пакетная загрузка остаётся активной."
        )
        await message.answer(
            "Этот файл не поддерживается. Пришлите фото, видео, анимацию либо "
            f"изображение/видео как документ. {suffix}"
        )
        return

    user_id = legacy_save._caller_user_id(message)
    if user_id is None:
        await message.answer("Не удалось определить пользователя.")
        return
    if workspace_service is not None:
        try:
            await legacy_save._require_workspace_save_access(
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
            "Ожидание файла уже истекло. Повторите <code>/save Имя</code> для одного "
            "файла или <code>/save_set Имя</code> для пакетной загрузки."
        )
        return

    character = None
    if active.character_id is not None:
        character = await load_character_by_id(
            database,
            character_id=active.character_id,
            workspace_id=active.workspace_id,
        )
        if character is None:
            save_upload_sessions.stop(chat_id=message.chat.id, user_id=user_id)
            await message.answer(
                "Персонаж был удалён из выбранного пространства. Сохранение отменено."
            )
            return

    save_kwargs: dict[str, Any] = {
        "request_message": message,
        "source_message": message,
        "character_name": character.name if character is not None else active.character_name,
        "actor_id": user_id,
        "workspace_id": active.workspace_id,
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
            + "\n\nСессия успела завершиться. Для следующего файла запустите команду снова."
        )
        return

    if updated.mode == "single":
        save_upload_sessions.stop(chat_id=message.chat.id, user_id=user_id)
        await message.answer(
            result
            + "\n\n<b>Одиночное сохранение завершено.</b> Для следующего файла "
            "снова используйте <code>/save Имя</code>."
        )
        return

    await message.answer(
        result
        + f"\n\n<b>Пакетная загрузка продолжается.</b> Обработано: "
        f"<b>{updated.saved_count}</b>. Пришлите следующий файл или завершите загрузку.",
        reply_markup=legacy_save._batch_save_keyboard(
            workspace_id=updated.workspace_id,
            character_id=int(updated.character_id or 0),
        ),
    )


__all__ = (
    "SaveModeCommandFilter",
    "handle_pending_save_upload",
    "handle_save_mode_command",
    "install_save_command_modes",
    "router",
)

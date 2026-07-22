from __future__ import annotations

from html import escape

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.onboarding import (
    DESTINATION_SPECS,
    WORKSPACE_DESTINATION_KEYS,
    WorkspaceDestinationKey,
    WorkspaceOnboardingRepository,
)
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService

router = Router(name=__name__)


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


def _destination_key(value: str) -> WorkspaceDestinationKey | None:
    if value not in WORKSPACE_DESTINATION_KEYS:
        return None
    return value  # type: ignore[return-value]


def _status_value(member) -> str:
    status = getattr(member, "status", "unknown")
    return str(getattr(status, "value", status))


def _target(value: str) -> int | str:
    cleaned = value.strip()
    if cleaned.lstrip("-").isdigit():
        return int(cleaned)
    if not cleaned.startswith("@"):
        cleaned = "@" + cleaned
    return cleaned


@router.message(Command("workspace_bind_channel"))
async def handle_workspace_bind_channel(
    message: Message,
    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    if message.chat.type != ChatType.PRIVATE:
        await message.answer(
            "Команда адресной привязки канала выполняется только в ЛС бота."
        )
        return
    parts = (message.text or "").split()
    key = _destination_key(parts[1].casefold()) if len(parts) > 1 else None
    if key is None or len(parts) < 3:
        await message.answer(
            "Формат: <code>/workspace_bind_channel НАЗНАЧЕНИЕ @channel [WORKSPACE_ID]</code>\n"
            "Назначения: <code>" + ", ".join(WORKSPACE_DESTINATION_KEYS) + "</code>"
        )
        return
    explicit_workspace_id = (
        int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None
    )
    user_id = message.from_user.id if message.from_user else 0
    global_owner = _is_global_owner(user_id)
    try:
        if explicit_workspace_id is not None:
            workspace = await workspace_service.set_active_workspace(
                workspace_id=explicit_workspace_id,
                user_id=user_id,
                global_owner=global_owner,
            )
        else:
            workspace = await workspace_service.resolve_active_workspace(
                user_id=user_id,
                global_owner=global_owner,
            )
        await workspace_service.require_role(
            workspace_id=workspace.id,
            user_id=user_id,
            minimum_role="admin",
            global_owner=global_owner,
        )
    except WorkspaceAccessError as error:
        await message.answer(str(error))
        return
    if workspace.is_system:
        await message.answer("Системный Velvet не настраивается пользовательским мастером.")
        return
    modules = await workspace_product_service.list_modules(
        workspace_id=workspace.id,
        actor_user_id=user_id,
        global_owner=global_owner,
    )
    enabled = {
        item.module_key
        for item in modules
        if item.is_allowed and item.is_enabled
    }
    spec = DESTINATION_SPECS[key]
    if key == "characters":
        await message.answer(
            "Форум персонажей подключается из самой супергруппы командой "
            "<code>/workspace_bind characters</code>. Канал не поддерживает "
            "персональные темы персонажей."
        )
        return
    if spec.module_keys and not any(item in enabled for item in spec.module_keys):
        await message.answer(
            f"Сначала включите модуль для назначения «{escape(spec.label)}» в "
            "/workspace_setup."
        )
        return
    try:
        chat = await bot.get_chat(_target(parts[2]))
        me = await bot.get_me()
        member = await bot.get_chat_member(chat.id, me.id)
    except TelegramAPIError as error:
        await message.answer(
            "Не удалось открыть канал или проверить права бота: " + escape(str(error))
        )
        return
    status = _status_value(member)
    if status not in {"administrator", "creator"}:
        await message.answer(
            "Бот должен быть администратором этого канала. Добавьте его и повторите команду."
        )
        return
    can_post = bool(getattr(member, "can_post_messages", False) or status == "creator")
    if chat.type == ChatType.CHANNEL and not can_post:
        await message.answer(
            "У бота нет права «Публикация сообщений» в этом канале."
        )
        return
    username = getattr(chat, "username", None)
    url = f"https://t.me/{username}" if username else None
    repository = WorkspaceOnboardingRepository(database)
    await repository.ensure_started(workspace_id=workspace.id, user_id=user_id)
    destination = await repository.upsert_destination(
        workspace_id=workspace.id,
        destination_key=key,
        chat_id=chat.id,
        message_thread_id=None,
        chat_type=str(getattr(chat.type, "value", chat.type)),
        chat_title=getattr(chat, "title", None),
        topic_title=None,
        url=url,
        bot_status=status,
        can_post=can_post or chat.type != ChatType.CHANNEL,
        can_manage_topics=bool(getattr(member, "can_manage_topics", False)),
        configured_by_user_id=user_id,
    )
    if spec.channel_kind is not None:
        try:
            await workspace_service.configure_channel(
                workspace_id=workspace.id,
                actor_user_id=user_id,
                kind=spec.channel_kind,
                chat_id=chat.id,
                url=url,
                global_owner=global_owner,
            )
        except (ValueError, WorkspaceAccessError) as error:
            await repository.delete_destination(
                workspace_id=workspace.id,
                destination_key=key,
            )
            await message.answer(str(error))
            return
    await message.answer(
        f"<b>✅ {escape(spec.label)} подключено</b>\n\n"
        f"Пространство: <b>{escape(workspace.name)}</b>\n"
        f"Канал: <b>{escape(destination.chat_title or str(destination.chat_id))}</b>\n"
        f"Chat ID: <code>{destination.chat_id}</code>\n\n"
        "Проверка сохранена. Откройте /workspace_setup_status."
    )


__all__ = ("router",)

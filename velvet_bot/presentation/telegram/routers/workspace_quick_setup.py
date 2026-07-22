from __future__ import annotations

from html import escape
from typing import cast

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.onboarding import (
    DESTINATION_SPECS,
    WorkspaceDestinationKey,
    WorkspaceOnboardingRepository,
    required_destination_keys,
)
from velvet_bot.domains.workspaces.product_models import WorkspaceModuleKey
from velvet_bot.domains.workspaces.product_service import (
    WorkspaceCreationAccessError,
    WorkspaceProductService,
)
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.workspace_ui import WorkspaceForm, workspace_callback

router = Router(name=__name__)


class WorkspaceQuickSetupCallback(CallbackData, prefix="wqs"):
    action: str
    workspace_id: int


class WorkspaceQuickSetupForm(StatesGroup):
    waiting_target = State()


def _quick_callback(action: str, workspace_id: int) -> str:
    return WorkspaceQuickSetupCallback(action=action, workspace_id=int(workspace_id)).pack()


def _parse_target(value: str) -> tuple[int | str, int | None]:
    parts = value.split()
    if not parts or len(parts) > 2:
        raise ValueError("Отправьте chat_id или @username. ID темы укажите вторым числом.")
    raw_chat = parts[0].strip()
    if raw_chat.lstrip("-").isdigit():
        target: int | str = int(raw_chat)
    else:
        target = raw_chat if raw_chat.startswith("@") else "@" + raw_chat
    thread_id: int | None = None
    if len(parts) == 2:
        if not parts[1].isdigit() or int(parts[1]) <= 0:
            raise ValueError("ID темы должен быть положительным числом.")
        thread_id = int(parts[1])
    return target, thread_id


def _status_value(member) -> str:
    status = getattr(member, "status", "unknown")
    return str(getattr(status, "value", status))


def _chat_url(chat) -> str | None:
    username = getattr(chat, "username", None)
    return f"https://t.me/{username}" if username else None


def _prompt_text(workspace: Workspace, key: WorkspaceDestinationKey) -> str:
    spec = DESTINATION_SPECS[key]
    if key == "characters":
        special = (
            "\n\nЭто должна быть форумная супергруппа. Боту нужны права администратора "
            "и «Управление темами»."
        )
    else:
        special = (
            "\n\nДля конкретной темы форума отправьте два числа: "
            "<code>-1001234567890 42</code>. Второе число — ID темы."
        )
    return (
        f"<b>⚡ Быстрая настройка · {escape(workspace.name)}</b>\n\n"
        f"Следующий пункт: {spec.emoji} <b>{escape(spec.label)}</b>\n"
        f"{escape(spec.description)}\n\n"
        "Добавьте бота администратором и отправьте сюда <code>chat_id</code> "
        "или <code>@username</code>."
        f"{special}"
    )


async def _workspace_for_user(
    *,
    workspace_id: int,
    user_id: int,
    workspace_service: WorkspaceService,
) -> Workspace:
    workspace = await workspace_service.set_active_workspace(
        workspace_id=int(workspace_id),
        user_id=int(user_id),
        global_owner=False,
    )
    await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=int(user_id),
        minimum_role="owner",
        global_owner=False,
    )
    if workspace.is_system:
        raise WorkspaceAccessError("Системное пространство нельзя настраивать этим мастером.")
    return workspace


async def _enabled_modules(
    *,
    workspace: Workspace,
    user_id: int,
    workspace_product_service: WorkspaceProductService,
) -> set[WorkspaceModuleKey]:
    modules = await workspace_product_service.list_modules(
        workspace_id=workspace.id,
        actor_user_id=int(user_id),
        global_owner=False,
    )
    return {
        item.module_key
        for item in modules
        if item.is_allowed and item.is_enabled
    }


async def _send_next_step(
    message: Message,
    *,
    state: FSMContext,
    database: Database,
    workspace: Workspace,
    user_id: int,
    workspace_product_service: WorkspaceProductService,
) -> None:
    repository = WorkspaceOnboardingRepository(database)
    await repository.ensure_started(workspace_id=workspace.id, user_id=user_id)
    await repository.mark_guide_viewed(workspace.id)
    await repository.mark_modules_confirmed(workspace.id)
    required = required_destination_keys(
        await _enabled_modules(
            workspace=workspace,
            user_id=user_id,
            workspace_product_service=workspace_product_service,
        )
    )
    configured = {
        item.destination_key for item in await repository.list_destinations(workspace.id)
    }
    missing = next((key for key in required if key not in configured), None)
    if missing is None:
        await repository.complete(workspace_id=workspace.id, user_id=user_id)
        await state.clear()
        await message.answer(
            f"<b>✅ {escape(workspace.name)} настроено</b>\n\n"
            "Все обязательные назначения подключены и проверены.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⚙️ Открыть пространство",
                            callback_data=workspace_callback(
                                "home",
                                workspace_id=workspace.id,
                            ),
                        )
                    ]
                ]
            ),
        )
        return
    await repository.set_step(workspace_id=workspace.id, step=f"quick_{missing}")
    await state.set_state(WorkspaceQuickSetupForm.waiting_target)
    await state.update_data(workspace_id=workspace.id, destination_key=missing)
    await message.answer(
        _prompt_text(workspace, missing),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✖ Остановить настройку",
                        callback_data=_quick_callback("cancel", workspace.id),
                    )
                ]
            ]
        ),
    )


@router.message(WorkspaceForm.waiting_workspace_name)
async def handle_workspace_name_and_start_quick_setup(
    message: Message,
    state: FSMContext,
    database: Database,
    workspace_product_service: WorkspaceProductService,
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    try:
        workspace = await workspace_product_service.create_personal_workspace(
            owner_user_id=user_id,
            name=(message.text or "").strip(),
        )
    except (ValueError, WorkspaceCreationAccessError) as error:
        await message.answer(str(error))
        return
    await state.clear()
    await message.answer(
        f"<b>✅ {escape(workspace.name)} создан</b>\n\n"
        "Архив приватный. Сейчас бот последовательно запросит чаты и каналы, "
        "которые нужны включённым модулям."
    )
    await _send_next_step(
        message,
        state=state,
        database=database,
        workspace=workspace,
        user_id=user_id,
        workspace_product_service=workspace_product_service,
    )


@router.message(Command("workspace_quick_setup"))
async def handle_workspace_quick_setup_command(
    message: Message,
    state: FSMContext,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    parts = (message.text or "").split()
    explicit_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    try:
        if explicit_id is None:
            workspace = await workspace_service.resolve_active_workspace(
                user_id=user_id,
                global_owner=False,
            )
        else:
            workspace = await _workspace_for_user(
                workspace_id=explicit_id,
                user_id=user_id,
                workspace_service=workspace_service,
            )
        await workspace_service.require_role(
            workspace_id=workspace.id,
            user_id=user_id,
            minimum_role="owner",
            global_owner=False,
        )
        if workspace.is_system:
            raise WorkspaceAccessError(
                "Системное пространство нельзя настраивать этим мастером."
            )
    except WorkspaceAccessError as error:
        await message.answer(str(error))
        return
    await _send_next_step(
        message,
        state=state,
        database=database,
        workspace=workspace,
        user_id=user_id,
        workspace_product_service=workspace_product_service,
    )


async def handle_workspace_quick_setup_callback(
    callback: CallbackQuery,
    callback_data: WorkspaceQuickSetupCallback,
    state: FSMContext,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    if callback_data.action == "cancel":
        await state.clear()
        await callback.answer("Настройка остановлена. Её можно продолжить через /start.")
        return
    if callback_data.action not in {"start", "resume"}:
        await callback.answer("Неизвестное действие.", show_alert=True)
        return
    try:
        workspace = await _workspace_for_user(
            workspace_id=callback_data.workspace_id,
            user_id=callback.from_user.id,
            workspace_service=workspace_service,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Откройте мастер в личных сообщениях бота.", show_alert=True)
        return
    await callback.answer()
    await _send_next_step(
        callback.message,
        state=state,
        database=database,
        workspace=workspace,
        user_id=callback.from_user.id,
        workspace_product_service=workspace_product_service,
    )


@router.message(WorkspaceQuickSetupForm.waiting_target)
async def handle_workspace_quick_setup_target(
    message: Message,
    state: FSMContext,
    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    data = await state.get_data()
    workspace_id = int(data.get("workspace_id") or 0)
    key_value = str(data.get("destination_key") or "")
    if workspace_id <= 0 or key_value not in DESTINATION_SPECS:
        await state.clear()
        await message.answer("Сессия настройки устарела. Запустите /workspace_quick_setup.")
        return
    key = cast(WorkspaceDestinationKey, key_value)
    user_id = message.from_user.id if message.from_user else 0
    try:
        workspace = await _workspace_for_user(
            workspace_id=workspace_id,
            user_id=user_id,
            workspace_service=workspace_service,
        )
        target, thread_id = _parse_target((message.text or "").strip())
        chat = await bot.get_chat(target)
        me = await bot.get_me()
        member = await bot.get_chat_member(chat.id, me.id)
    except (ValueError, WorkspaceAccessError) as error:
        await message.answer(str(error))
        return
    except TelegramAPIError as error:
        await message.answer(
            "Не удалось открыть чат или проверить права бота: " + escape(str(error))
        )
        return
    status = _status_value(member)
    is_admin = status in {"administrator", "creator"}
    if not is_admin:
        await message.answer("Бот должен быть администратором указанного чата или канала.")
        return
    can_manage_topics = bool(getattr(member, "can_manage_topics", False))
    if key == "characters":
        if chat.type != ChatType.SUPERGROUP or not bool(getattr(chat, "is_forum", False)):
            await message.answer(
                "Для персонажей нужна форумная супергруппа с включёнными темами."
            )
            return
        if not can_manage_topics:
            await message.answer("Выдайте боту право «Управление темами».")
            return
        thread_id = None
    can_post = bool(
        is_admin
        or getattr(member, "can_post_messages", False)
        or getattr(member, "can_send_messages", False)
    )
    if not can_post:
        await message.answer("У бота нет права отправлять сообщения в это назначение.")
        return
    spec = DESTINATION_SPECS[key]
    repository = WorkspaceOnboardingRepository(database)
    try:
        destination = await repository.upsert_destination(
            workspace_id=workspace.id,
            destination_key=key,
            chat_id=chat.id,
            message_thread_id=thread_id,
            chat_type=str(getattr(chat.type, "value", chat.type)),
            chat_title=getattr(chat, "title", None),
            topic_title=f"Тема {thread_id}" if thread_id is not None else None,
            url=_chat_url(chat),
            bot_status=status,
            can_post=can_post,
            can_manage_topics=can_manage_topics,
            configured_by_user_id=user_id,
        )
        if spec.channel_kind is not None:
            try:
                await workspace_service.configure_channel(
                    workspace_id=workspace.id,
                    actor_user_id=user_id,
                    kind=spec.channel_kind,
                    chat_id=chat.id,
                    url=destination.url,
                    global_owner=False,
                )
            except (ValueError, WorkspaceAccessError):
                await repository.delete_destination(
                    workspace_id=workspace.id,
                    destination_key=key,
                )
                raise
    except (ValueError, WorkspaceAccessError) as error:
        await message.answer(str(error))
        return
    await message.answer(
        f"✅ {spec.label} подключено: <code>{destination.chat_id}</code>"
        + (
            f" · тема <code>{destination.message_thread_id}</code>"
            if destination.message_thread_id is not None
            else ""
        )
    )
    await _send_next_step(
        message,
        state=state,
        database=database,
        workspace=workspace,
        user_id=user_id,
        workspace_product_service=workspace_product_service,
    )


router.callback_query.register(
    handle_workspace_quick_setup_callback,
    WorkspaceQuickSetupCallback.filter(),
)


__all__ = (
    "WorkspaceQuickSetupCallback",
    "WorkspaceQuickSetupForm",
    "router",
)

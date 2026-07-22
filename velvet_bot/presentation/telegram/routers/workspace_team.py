from __future__ import annotations

from html import escape
from typing import cast

import asyncpg
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.domains.workspaces.team_repository import WorkspaceTeamRepository
from velvet_bot.domains.workspaces.team_service import WorkspaceTeamService
from velvet_bot.workspace_team_ui import (
    ROLE_LABELS,
    WorkspaceTeamCallback,
    WorkspaceTeamForm,
    build_member_keyboard,
    build_new_member_role_keyboard,
    build_remove_confirmation_keyboard,
    build_team_keyboard,
    format_member,
    format_team,
)
from velvet_bot.workspace_ui import WorkspaceCallback

router = Router(name=__name__)


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


def _team_service(database: Database, workspaces: WorkspaceService) -> WorkspaceTeamService:
    return WorkspaceTeamService(
        repository=WorkspaceTeamRepository(database),
        workspaces=workspaces,
    )


async def _module_enabled(database: Database, workspace_id: int) -> bool:
    async with database.acquire() as connection:
        value = await connection.fetchval(
            """
            SELECT is_allowed AND is_enabled
            FROM workspace_modules
            WHERE workspace_id = $1::BIGINT
              AND module_key = 'team'
            """,
            int(workspace_id),
        )
    return bool(value)


async def _require_context(
    *,
    database: Database,
    workspaces: WorkspaceService,
    workspace_id: int,
    actor_user_id: int,
) -> tuple[Workspace, WorkspaceMembership]:
    global_owner = _is_global_owner(actor_user_id)
    active = await workspaces.resolve_active_workspace(
        user_id=actor_user_id,
        global_owner=global_owner,
    )
    if active.id != int(workspace_id):
        raise WorkspaceAccessError(
            "Кнопка относится не к активному пространству. Откройте меню заново."
        )
    if active.is_system:
        raise WorkspaceAccessError(
            "Команда системного Velvet управляется глобальными настройками."
        )
    membership = await workspaces.require_role(
        workspace_id=active.id,
        user_id=actor_user_id,
        minimum_role="admin",
        global_owner=global_owner,
    )
    if not await _module_enabled(database, active.id):
        raise WorkspaceAccessError("Модуль команды выключен или не разрешён Стэл.")
    return active, membership


async def _edit(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup,
) -> None:
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                await callback.message.answer(text, reply_markup=reply_markup)
    await callback.answer()


async def _show_team(
    callback: CallbackQuery,
    *,
    database: Database,
    workspaces: WorkspaceService,
    workspace_id: int,
) -> None:
    actor_id = int(callback.from_user.id)
    workspace, _ = await _require_context(
        database=database,
        workspaces=workspaces,
        workspace_id=workspace_id,
        actor_user_id=actor_id,
    )
    members = await _team_service(database, workspaces).list_members(
        workspace_id=workspace.id,
        actor_user_id=actor_id,
        global_owner=_is_global_owner(actor_id),
    )
    await _edit(
        callback,
        text=format_team(workspace_name=workspace.name, members=members),
        reply_markup=build_team_keyboard(
            workspace_id=workspace.id,
            members=members,
        ),
    )


@router.callback_query(
    WorkspaceCallback.filter((F.action == "module") & (F.module_key == "team"))
)
async def handle_team_module(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    try:
        await _show_team(
            callback,
            database=database,
            workspaces=workspace_service,
            workspace_id=callback_data.workspace_id,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)


@router.callback_query(WorkspaceTeamCallback.filter())
async def handle_team_callback(
    callback: CallbackQuery,
    callback_data: WorkspaceTeamCallback,
    state: FSMContext,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    actor_id = int(callback.from_user.id)
    try:
        workspace, actor = await _require_context(
            database=database,
            workspaces=workspace_service,
            workspace_id=callback_data.workspace_id,
            actor_user_id=actor_id,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return

    service = _team_service(database, workspace_service)
    repository = WorkspaceTeamRepository(database)
    action = callback_data.action

    if action == "list":
        await state.clear()
        await _show_team(
            callback,
            database=database,
            workspaces=workspace_service,
            workspace_id=workspace.id,
        )
        return
    if action == "add":
        await state.set_state(WorkspaceTeamForm.waiting_user_id)
        await state.update_data(workspace_id=workspace.id)
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "<b>Добавление участника</b>\n\n"
                "Отправьте числовой Telegram ID пользователя. Узнать его можно через "
                "служебного ID-бота или из логов вашего приложения."
            )
        await callback.answer()
        return
    if action == "addrole":
        try:
            role = cast(WorkspaceRole, callback_data.role)
            if role not in ROLE_LABELS:
                raise ValueError("Неизвестная роль команды.")
            await service.add_member(
                workspace_id=workspace.id,
                actor_user_id=actor_id,
                user_id=callback_data.user_id,
                role=role,
                global_owner=_is_global_owner(actor_id),
            )
        except (WorkspaceAccessError, ValueError) as error:
            await callback.answer(str(error), show_alert=True)
            return
        await callback.answer(f"Участник добавлен: {ROLE_LABELS[role]}.")
        members = await service.list_members(
            workspace_id=workspace.id,
            actor_user_id=actor_id,
            global_owner=_is_global_owner(actor_id),
        )
        await _edit(
            callback,
            text=format_team(workspace_name=workspace.name, members=members),
            reply_markup=build_team_keyboard(workspace_id=workspace.id, members=members),
        )
        return

    target = await repository.get_member(
        workspace_id=workspace.id,
        user_id=callback_data.user_id,
    )
    if target is None:
        await callback.answer("Участник больше не состоит в команде.", show_alert=True)
        return

    if action == "member":
        await _edit(
            callback,
            text=format_member(target),
            reply_markup=build_member_keyboard(
                workspace_id=workspace.id,
                item=target,
                actor_role=actor.role,
            ),
        )
        return
    if action == "remove":
        await _edit(
            callback,
            text=(
                "<b>Удалить участника?</b>\n\n"
                f"Telegram ID: <code>{target.user_id}</code>\n"
                f"Роль: <b>{ROLE_LABELS[target.role]}</b>\n\n"
                "После удаления активное пространство пользователя будет сброшено."
            ),
            reply_markup=build_remove_confirmation_keyboard(
                workspace_id=workspace.id,
                user_id=target.user_id,
            ),
        )
        return

    try:
        if action == "role":
            role = cast(WorkspaceRole, callback_data.role)
            if role not in ROLE_LABELS:
                raise ValueError("Неизвестная роль команды.")
            await service.change_role(
                workspace_id=workspace.id,
                actor_user_id=actor_id,
                user_id=target.user_id,
                role=role,
                global_owner=_is_global_owner(actor_id),
            )
            await callback.answer(f"Роль изменена: {ROLE_LABELS[role]}.")
        elif action == "removeok":
            await service.remove_member(
                workspace_id=workspace.id,
                actor_user_id=actor_id,
                user_id=target.user_id,
                global_owner=_is_global_owner(actor_id),
            )
            await callback.answer("Участник удалён.")
        else:
            await callback.answer("Неизвестное действие команды.", show_alert=True)
            return
    except (WorkspaceAccessError, ValueError, asyncpg.CheckViolationError) as error:
        await callback.answer(str(error), show_alert=True)
        return

    members = await service.list_members(
        workspace_id=workspace.id,
        actor_user_id=actor_id,
        global_owner=_is_global_owner(actor_id),
    )
    await _edit(
        callback,
        text=format_team(workspace_name=workspace.name, members=members),
        reply_markup=build_team_keyboard(workspace_id=workspace.id, members=members),
    )


@router.message(
    StateFilter(WorkspaceTeamForm.waiting_user_id),
    F.text,
)
async def handle_team_user_id(
    message: Message,
    state: FSMContext,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    actor_id = int(message.from_user.id) if message.from_user else 0
    data = await state.get_data()
    workspace_id = int(data.get("workspace_id") or 0)
    try:
        _, actor = await _require_context(
            database=database,
            workspaces=workspace_service,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
        )
    except WorkspaceAccessError as error:
        await state.clear()
        await message.answer(escape(str(error)))
        return
    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("Telegram ID должен быть положительным числом.")
        return
    target_user_id = int(raw)
    if target_user_id == actor_id:
        await message.answer("Вы уже состоите в команде. Это было бы необычно забыть.")
        return
    existing = await WorkspaceTeamRepository(database).get_member(
        workspace_id=workspace_id,
        user_id=target_user_id,
    )
    if existing is not None:
        await message.answer(
            f"Пользователь уже состоит в команде как <b>{ROLE_LABELS[existing.role]}</b>."
        )
        return
    await state.clear()
    await message.answer(
        "<b>Выберите роль нового участника</b>\n\n"
        f"Telegram ID: <code>{target_user_id}</code>",
        reply_markup=build_new_member_role_keyboard(
            workspace_id=workspace_id,
            user_id=target_user_id,
            actor_role=actor.role,
        ),
    )


__all__ = ("router",)

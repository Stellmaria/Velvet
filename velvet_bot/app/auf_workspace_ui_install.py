from __future__ import annotations

import importlib
from typing import Any

from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot import workspace_ui
from velvet_bot.core.config.kie import KieSettings
from velvet_bot.domains.auf_runtime import (
    AUF_MODULE_KEY,
    AUF_WORKSPACE_ACTION,
    AufRuntimeAccessError,
    AufRuntimeRepository,
    AufRuntimeService,
)
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.routers.workspace_auf_root import build_auf_root_view

_INSTALLED = False


async def handle_auf_workspace_command(
    message: Message,
    state: FSMContext,
    workspace_service: WorkspaceService,
    kie_settings: KieSettings,
    auf_runtime_service: AufRuntimeService,
) -> None:
    """Open Auf for the caller's active personal workspace."""

    user_id = message.from_user.id if message.from_user else 0
    try:
        workspace = await workspace_service.resolve_active_workspace(
            user_id=user_id,
            global_owner=auf_runtime_service.is_global_owner(user_id),
        )
        text, keyboard = await build_auf_root_view(
            workspace_id=workspace.id,
            user_id=user_id,
            kie_settings=kie_settings,
            auf_runtime_service=auf_runtime_service,
        )
    except (WorkspaceAccessError, AufRuntimeAccessError, ValueError) as error:
        await message.answer(str(error))
        return

    await state.clear()
    await message.answer(text, reply_markup=keyboard)


def install_auf_workspace_ui() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    workspace_ui.MODULE_LABELS[AUF_MODULE_KEY] = "🐕 Ауф · генерация"
    workspace_ui.MODULE_HELP[AUF_MODULE_KEY] = (
        "Создание изображений и видео. Владелец пространства включает модуль "
        "и задаёт допустимую параллельность задач."
    )

    presentation = importlib.import_module(
        "velvet_bot.presentation.telegram.workspace_home_presentation"
    )
    controller = importlib.import_module(
        "velvet_bot.presentation.telegram.workspace_home_controller"
    )
    workspaces_router = importlib.import_module(
        "velvet_bot.presentation.telegram.routers.workspaces"
    )
    original_home = presentation.build_workspace_home_presentation
    original_modules_keyboard = workspace_ui.build_modules_keyboard
    original_register = controller.register_workspace_home

    async def build_home_with_auf_visibility(**kwargs: Any):
        product_service = kwargs["workspace_product_service"]
        database = product_service._product._database
        # The keyword is retained because the controller signature is part of the
        # current dependency-injection contract.
        kwargs["auf_runtime_service"] = AufRuntimeService(
            AufRuntimeRepository(database)
        )
        return await original_home(**kwargs)

    def build_modules_with_auf_entry(workspace_id: int, modules):
        markup = original_modules_keyboard(workspace_id, modules)
        rows = [list(row) for row in markup.inline_keyboard]
        for row in rows:
            if row and "Ауф · генерация" in row[0].text:
                row.append(
                    InlineKeyboardButton(
                        text="Открыть",
                        callback_data=workspace_ui.workspace_callback(
                            AUF_WORKSPACE_ACTION,
                            workspace_id=workspace_id,
                        ),
                    )
                )
                break
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def register_workspace_home_with_auf_command(router) -> None:
        # Register before FSM handlers so /auf is also a recovery entry from an
        # interrupted generation form. The handler still checks active workspace,
        # ownership and module policy through AufRuntimeService.
        router.message.register(handle_auf_workspace_command, Command("auf"))
        original_register(router)

    presentation.build_workspace_home_presentation = build_home_with_auf_visibility
    controller.build_workspace_home_presentation = build_home_with_auf_visibility
    controller.register_workspace_home = register_workspace_home_with_auf_command
    workspace_ui.build_modules_keyboard = build_modules_with_auf_entry
    workspaces_router.build_modules_keyboard = build_modules_with_auf_entry
    _INSTALLED = True


__all__ = ("handle_auf_workspace_command", "install_auf_workspace_ui")

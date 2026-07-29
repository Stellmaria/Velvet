from __future__ import annotations

import importlib
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot import workspace_ui
from velvet_bot.core.access import policy
from velvet_bot.domains.meow_runtime import MeowRuntimeRepository, MeowRuntimeService

_INSTALLED = False


def install_meow_workspace_ui() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    workspace_ui.MODULE_LABELS["meow"] = "🐕 Ауф · генерация"
    workspace_ui.MODULE_HELP["meow"] = (
        "Создание изображений и видео через Kie.ai и GRS AI. Стэл разрешает модуль, "
        "владелец пространства включает его и задаёт параллельность до 20 задач."
    )

    callback_prefixes = list(policy.WORKSPACE_MEMBER_CALLBACK_PREFIXES)
    for prefix in ("meow:", "mrt:", "meowv|"):
        if prefix not in callback_prefixes:
            callback_prefixes.append(prefix)
    policy.WORKSPACE_MEMBER_CALLBACK_PREFIXES = tuple(callback_prefixes)

    state_prefixes = list(policy.WORKSPACE_MEMBER_FSM_STATE_PREFIXES)
    for prefix in ("MeowForm:", "MeowVideoForm:", "MeowRuntimeForm:"):
        if prefix not in state_prefixes:
            state_prefixes.append(prefix)
    policy.WORKSPACE_MEMBER_FSM_STATE_PREFIXES = tuple(state_prefixes)

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

    async def build_home_with_meow_visibility(**kwargs: Any):
        product_service = kwargs["workspace_product_service"]
        database = product_service._product._database
        kwargs["meow_runtime_service"] = MeowRuntimeService(
            MeowRuntimeRepository(database)
        )
        return await original_home(**kwargs)

    def build_modules_with_meow_entry(workspace_id: int, modules):
        markup = original_modules_keyboard(workspace_id, modules)
        rows = [list(row) for row in markup.inline_keyboard]
        for row in rows:
            if row and "Ауф · генерация" in row[0].text:
                row.append(
                    InlineKeyboardButton(
                        text="Открыть",
                        callback_data=workspace_ui.workspace_callback(
                            "meow",
                            workspace_id=workspace_id,
                        ),
                    )
                )
                break
        return InlineKeyboardMarkup(inline_keyboard=rows)

    presentation.build_workspace_home_presentation = build_home_with_meow_visibility
    controller.build_workspace_home_presentation = build_home_with_meow_visibility
    workspace_ui.build_modules_keyboard = build_modules_with_meow_entry
    workspaces_router.build_modules_keyboard = build_modules_with_meow_entry
    _INSTALLED = True


__all__ = ("install_meow_workspace_ui",)

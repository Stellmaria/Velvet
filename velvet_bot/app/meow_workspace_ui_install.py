from __future__ import annotations

import importlib
from typing import Any

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
    original = presentation.build_workspace_home_presentation

    async def build_home_with_meow_visibility(**kwargs: Any):
        product_service = kwargs["workspace_product_service"]
        database = product_service._product._database
        kwargs["meow_runtime_service"] = MeowRuntimeService(
            MeowRuntimeRepository(database)
        )
        return await original(**kwargs)

    presentation.build_workspace_home_presentation = build_home_with_meow_visibility
    controller.build_workspace_home_presentation = build_home_with_meow_visibility
    _INSTALLED = True


__all__ = ("install_meow_workspace_ui",)

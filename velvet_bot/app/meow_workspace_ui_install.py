from __future__ import annotations

from velvet_bot.core.access import policy
from velvet_bot import workspace_ui

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

    _INSTALLED = True


__all__ = ("install_meow_workspace_ui",)

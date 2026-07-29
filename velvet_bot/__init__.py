"""Velvet Telegram bot package."""

from velvet_bot import workspace_ui as _workspace_ui

# Module catalog entries must exist during imports, tests and owner admin screens,
# not only after the runtime application installers have executed.
_workspace_ui.MODULE_LABELS["meow"] = "🐕 Ауф · генерация"
_workspace_ui.MODULE_HELP["meow"] = (
    "Создание изображений и видео через Kie.ai и GRS AI. Стэл разрешает модуль, "
    "владелец пространства включает его и задаёт параллельность до 20 задач."
)

del _workspace_ui

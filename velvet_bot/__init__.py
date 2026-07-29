"""Velvet Telegram bot package."""

from __future__ import annotations

import importlib
from typing import Any, cast

# Keep the module catalog complete during runtime imports and tests without a
# static workspace_ui import. A static import here makes bounded mypy follow the
# entire Telegram presentation graph, which rather defeats the word "bounded".
_workspace_ui = cast(Any, importlib.import_module("velvet_bot.workspace_ui"))
_workspace_ui.MODULE_LABELS["meow"] = "🐕 Ауф · генерация"
_workspace_ui.MODULE_HELP["meow"] = (
    "Создание изображений и видео через Kie.ai и GRS AI. Стэл разрешает модуль, "
    "владелец пространства включает его и задаёт параллельность до 20 задач."
)

del _workspace_ui

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from aiogram.types import InlineKeyboardMarkup

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.presentation.telegram.routers.workspace_owner_controls import (
    _archive_dashboard_keyboard as _legacy_archive_dashboard_keyboard,
    _load_archive_characters as _legacy_load_archive_characters,
)


@dataclass(frozen=True, slots=True)
class WorkspaceArchiveDashboard:
    """Ready-to-render personal archive dashboard presentation."""

    text: str
    keyboard: InlineKeyboardMarkup
    character_count: int


async def build_workspace_archive_dashboard(
    database: Database,
    workspace: Workspace,
    *,
    command_context: bool = False,
) -> WorkspaceArchiveDashboard:
    """Build the canonical archive dashboard without leaking legacy helpers."""

    rows = await _legacy_load_archive_characters(
        database,
        workspace_id=workspace.id,
    )
    character_count = len(rows)
    if command_context:
        description = (
            "Здесь показаны материалы только активного пользовательского "
            "пространства."
        )
    else:
        description = (
            "Выберите персонажа, чтобы открыть сохранённые фото, видео и документы. "
            "Пустые архивы остаются видимыми, чтобы было понятно, куда ещё ничего "
            "не положили."
        )
    return WorkspaceArchiveDashboard(
        text=(
            f"<b>🖼 Архив · {escape(workspace.name)}</b>\n\n"
            f"Персонажей: <b>{character_count}</b>\n\n"
            f"{description}"
        ),
        keyboard=_legacy_archive_dashboard_keyboard(
            workspace_id=workspace.id,
            rows=rows,
        ),
        character_count=character_count,
    )


__all__ = (
    "WorkspaceArchiveDashboard",
    "build_workspace_archive_dashboard",
)

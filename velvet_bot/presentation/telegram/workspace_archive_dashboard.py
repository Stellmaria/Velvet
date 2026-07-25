from __future__ import annotations

from dataclasses import dataclass
from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.presentation.telegram.workspace_personal_archive_contract import (
    workspace_personal_archive_callback,
)
from velvet_bot.workspace_ui import workspace_callback


@dataclass(frozen=True, slots=True)
class WorkspaceArchiveCharacter:
    """Character summary used by the personal archive dashboard."""

    id: int
    name: str
    archive_topic_url: str | None
    media_count: int


@dataclass(frozen=True, slots=True)
class WorkspaceArchiveDashboard:
    """Ready-to-render personal archive dashboard presentation."""

    text: str
    keyboard: InlineKeyboardMarkup
    character_count: int


async def load_workspace_archive_characters(
    database: Database,
    *,
    workspace_id: int,
) -> tuple[WorkspaceArchiveCharacter, ...]:
    """Load typed archive dashboard rows for one workspace."""

    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                character.id,
                character.name,
                character.archive_topic_url,
                COUNT(link.media_id) AS media_count
            FROM characters AS character
            LEFT JOIN character_media AS link
              ON link.character_id = character.id
            WHERE character.workspace_id = $1::BIGINT
            GROUP BY character.id
            ORDER BY character.normalized_name, character.id
            LIMIT 60
            """,
            int(workspace_id),
        )
    return tuple(
        WorkspaceArchiveCharacter(
            id=int(row["id"]),
            name=str(row["name"]),
            archive_topic_url=(
                str(row["archive_topic_url"])
                if row["archive_topic_url"]
                else None
            ),
            media_count=int(row["media_count"] or 0),
        )
        for row in rows
    )


def build_workspace_archive_dashboard_keyboard(
    *,
    workspace_id: int,
    characters: tuple[WorkspaceArchiveCharacter, ...],
) -> InlineKeyboardMarkup:
    """Build the canonical character list keyboard for a personal archive."""

    buttons: list[list[InlineKeyboardButton]] = []
    for character in characters:
        if character.media_count:
            button = InlineKeyboardButton(
                text=f"🖼 {character.name} · {character.media_count}"[:60],
                callback_data=workspace_personal_archive_callback(
                    "open",
                    workspace_id=workspace_id,
                    character_id=character.id,
                ),
            )
        elif character.archive_topic_url:
            button = InlineKeyboardButton(
                text=f"📂 {character.name} · пусто"[:60],
                url=character.archive_topic_url,
            )
        else:
            button = InlineKeyboardButton(
                text=f"➖ {character.name} · пусто"[:60],
                callback_data=workspace_personal_archive_callback(
                    "empty",
                    workspace_id=workspace_id,
                    character_id=character.id,
                ),
            )
        buttons.append([button])
    buttons.extend(
        [
            [
                InlineKeyboardButton(
                    text="➕ Как сохранить материал",
                    callback_data=workspace_personal_archive_callback(
                        "help",
                        workspace_id=workspace_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Моё пространство",
                    callback_data=workspace_callback(
                        "home",
                        workspace_id=workspace_id,
                    ),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_workspace_archive_dashboard(
    database: Database,
    workspace: Workspace,
    *,
    command_context: bool = False,
) -> WorkspaceArchiveDashboard:
    """Build the canonical archive dashboard presentation."""

    characters = await load_workspace_archive_characters(
        database,
        workspace_id=workspace.id,
    )
    character_count = len(characters)
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
        keyboard=build_workspace_archive_dashboard_keyboard(
            workspace_id=workspace.id,
            characters=characters,
        ),
        character_count=character_count,
    )


__all__ = (
    "WorkspaceArchiveCharacter",
    "WorkspaceArchiveDashboard",
    "build_workspace_archive_dashboard",
    "build_workspace_archive_dashboard_keyboard",
    "load_workspace_archive_characters",
)

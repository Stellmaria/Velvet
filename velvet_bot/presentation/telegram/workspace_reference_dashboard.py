from __future__ import annotations

from dataclasses import dataclass
from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.workspace_ui import workspace_callback

_REFERENCE_CALLBACK_PREFIX = "wref"


@dataclass(frozen=True, slots=True)
class WorkspaceReferenceAction:
    action: str
    workspace_id: int
    character_id: int = 0


@dataclass(frozen=True, slots=True)
class WorkspaceReferenceCharacter:
    id: int
    name: str
    reference_count: int


@dataclass(frozen=True, slots=True)
class WorkspaceReferenceDashboard:
    text: str
    keyboard: InlineKeyboardMarkup
    character_count: int


def workspace_reference_callback(
    action: str,
    *,
    workspace_id: int,
    character_id: int = 0,
) -> str:
    return (
        f"{_REFERENCE_CALLBACK_PREFIX}:{action}:"
        f"{int(workspace_id)}:{int(character_id)}"
    )


def parse_workspace_reference_callback(
    data: str | None,
) -> WorkspaceReferenceAction | None:
    if not data:
        return None
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != _REFERENCE_CALLBACK_PREFIX:
        return None
    try:
        workspace_id = int(parts[2])
        character_id = int(parts[3])
    except ValueError:
        return None
    return WorkspaceReferenceAction(
        action=parts[1],
        workspace_id=workspace_id,
        character_id=character_id,
    )


async def load_workspace_reference_characters(
    database: Database,
    *,
    workspace_id: int,
) -> tuple[WorkspaceReferenceCharacter, ...]:
    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                character.id,
                character.name,
                COUNT(reference.id) AS reference_count
            FROM characters AS character
            LEFT JOIN character_references AS reference
              ON reference.workspace_id = character.workspace_id
             AND reference.character_id = character.id
            WHERE character.workspace_id = $1::BIGINT
            GROUP BY character.id
            ORDER BY character.normalized_name, character.id
            LIMIT 60
            """,
            int(workspace_id),
        )
    return tuple(
        WorkspaceReferenceCharacter(
            id=int(row["id"]),
            name=str(row["name"]),
            reference_count=int(row["reference_count"] or 0),
        )
        for row in rows
    )


def build_workspace_reference_dashboard_keyboard(
    *,
    workspace_id: int,
    characters: tuple[WorkspaceReferenceCharacter, ...],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"🧬 {character.name} · {character.reference_count}"[:60],
                callback_data=workspace_reference_callback(
                    "open",
                    workspace_id=workspace_id,
                    character_id=character.id,
                ),
            )
        ]
        for character in characters
    ]
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="➕ Как добавить референс",
                    callback_data=workspace_reference_callback(
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
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def build_workspace_reference_dashboard(
    database: Database,
    workspace: Workspace,
) -> WorkspaceReferenceDashboard:
    characters = await load_workspace_reference_characters(
        database,
        workspace_id=workspace.id,
    )
    text = (
        f"<b>🧬 Референсы · {escape(workspace.name)}</b>\n\n"
        f"Персонажей: <b>{len(characters)}</b>\n\n"
        "Выберите персонажа, чтобы открыть его личную библиотеку референсов."
    )
    return WorkspaceReferenceDashboard(
        text=text,
        keyboard=build_workspace_reference_dashboard_keyboard(
            workspace_id=workspace.id,
            characters=characters,
        ),
        character_count=len(characters),
    )


__all__ = (
    "WorkspaceReferenceAction",
    "WorkspaceReferenceCharacter",
    "WorkspaceReferenceDashboard",
    "build_workspace_reference_dashboard",
    "build_workspace_reference_dashboard_keyboard",
    "load_workspace_reference_characters",
    "parse_workspace_reference_callback",
    "workspace_reference_callback",
)

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery

_PREFIX = "wpa"


@dataclass(frozen=True, slots=True)
class WorkspacePersonalArchiveAction:
    action: str
    workspace_id: int
    character_id: int = 0
    offset: int = 0
    media_id: int = 0


def workspace_personal_archive_callback(
    action: str,
    *,
    workspace_id: int,
    character_id: int = 0,
    offset: int = 0,
    media_id: int = 0,
) -> str:
    """Build the stable callback payload without importing the legacy owner router."""

    return ":".join(
        (
            _PREFIX,
            str(action),
            str(int(workspace_id)),
            str(int(character_id)),
            str(max(0, int(offset))),
            str(int(media_id)),
        )
    )


def parse_workspace_personal_archive_callback(
    data: str | None,
) -> WorkspacePersonalArchiveAction | None:
    """Parse one stable ``wpa`` payload into a typed immutable value."""

    if not data:
        return None
    parts = data.split(":")
    if len(parts) != 6 or parts[0] != _PREFIX or not parts[1]:
        return None
    try:
        workspace_id, character_id, offset, media_id = (
            int(parts[2]),
            int(parts[3]),
            int(parts[4]),
            int(parts[5]),
        )
    except ValueError:
        return None
    if workspace_id < 0 or character_id < 0 or offset < 0 or media_id < 0:
        return None
    return WorkspacePersonalArchiveAction(
        action=parts[1],
        workspace_id=workspace_id,
        character_id=character_id,
        offset=offset,
        media_id=media_id,
    )


class WorkspacePersonalArchiveActionFilter(BaseFilter):
    """Match selected ``wpa`` actions without declaring a duplicate CallbackData class."""

    def __init__(self, *actions: str) -> None:
        self.actions = frozenset(actions)

    async def __call__(
        self,
        callback: CallbackQuery,
    ) -> bool | dict[str, Any]:
        parsed = parse_workspace_personal_archive_callback(callback.data)
        if parsed is None or parsed.action not in self.actions:
            return False
        return {"archive_action": parsed}


__all__ = (
    "WorkspacePersonalArchiveAction",
    "WorkspacePersonalArchiveActionFilter",
    "parse_workspace_personal_archive_callback",
    "workspace_personal_archive_callback",
)

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, TypeAlias

WorkspaceModuleKey: TypeAlias = Literal[
    "characters",
    "archive",
    "taxonomy",
    "references",
    "public_archive",
    "watermark",
    "qwen",
    "publications",
    "analytics",
    "team",
]

WORKSPACE_MODULE_KEYS: Final[tuple[WorkspaceModuleKey, ...]] = (
    "characters",
    "archive",
    "taxonomy",
    "references",
    "public_archive",
    "watermark",
    "qwen",
    "publications",
    "analytics",
    "team",
)

DEFAULT_PERSONAL_MODULE_KEYS: Final[tuple[WorkspaceModuleKey, ...]] = (
    "characters",
    "archive",
    "taxonomy",
    "references",
    "public_archive",
)

GLOBAL_WORKSPACE_CREATOR_ID: Final[int] = 7221553045


@dataclass(frozen=True, slots=True)
class WorkspaceCreationGrant:
    user_id: int
    granted_by_user_id: int
    allowed_modules: tuple[WorkspaceModuleKey, ...]
    max_workspaces: int
    is_active: bool
    granted_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceModuleSetting:
    workspace_id: int
    module_key: WorkspaceModuleKey
    is_allowed: bool
    is_enabled: bool
    updated_by_user_id: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceCategory:
    id: int
    workspace_id: int
    key: str
    label: str
    emoji: str
    sort_order: int
    is_enabled: bool


@dataclass(frozen=True, slots=True)
class WorkspaceUniverse:
    id: int
    workspace_id: int
    key: str
    label: str
    emoji: str
    requires_story: bool
    sort_order: int
    is_enabled: bool
    source_workspace_id: int | None
    source_universe_key: str | None


@dataclass(frozen=True, slots=True)
class WorkspaceStory:
    id: int
    workspace_id: int
    universe_key: str
    key: str
    short_label: str
    title: str
    sort_order: int
    is_enabled: bool
    source_story_id: int | None


__all__ = (
    "DEFAULT_PERSONAL_MODULE_KEYS",
    "GLOBAL_WORKSPACE_CREATOR_ID",
    "WORKSPACE_MODULE_KEYS",
    "WorkspaceCategory",
    "WorkspaceCreationGrant",
    "WorkspaceModuleKey",
    "WorkspaceModuleSetting",
    "WorkspaceStory",
    "WorkspaceUniverse",
)

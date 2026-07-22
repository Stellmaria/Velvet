from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, TypeAlias

DEFAULT_WORKSPACE_ID: Final[int] = 1
SYSTEM_WORKSPACE_SLUG: Final[str] = "velvet"

WorkspaceRole: TypeAlias = Literal[
    "owner",
    "admin",
    "editor",
    "reviewer",
    "viewer",
]
WorkspaceChannelKind: TypeAlias = Literal[
    "archive",
    "public",
    "download",
    "publication",
    "adult",
    "discussion",
    "logs",
    "analytics",
]
WorkspaceDownloadsMode: TypeAlias = Literal[
    "disabled",
    "watermark",
    "original",
    "subscription",
]
WorkspaceDownloadAudience: TypeAlias = Literal["disabled", "all", "subscribers"]
WorkspaceDownloadVariant: TypeAlias = Literal["watermark", "original"]

WORKSPACE_ROLES: Final[tuple[WorkspaceRole, ...]] = (
    "owner",
    "admin",
    "editor",
    "reviewer",
    "viewer",
)
WORKSPACE_CHANNEL_KINDS: Final[tuple[WorkspaceChannelKind, ...]] = (
    "archive",
    "public",
    "download",
    "publication",
    "adult",
    "discussion",
    "logs",
    "analytics",
)
WORKSPACE_DOWNLOAD_MODES: Final[tuple[WorkspaceDownloadsMode, ...]] = (
    "disabled",
    "watermark",
    "original",
    "subscription",
)
WORKSPACE_DOWNLOAD_AUDIENCES: Final[tuple[WorkspaceDownloadAudience, ...]] = (
    "disabled",
    "all",
    "subscribers",
)
WORKSPACE_DOWNLOAD_VARIANTS: Final[tuple[WorkspaceDownloadVariant, ...]] = (
    "watermark",
    "original",
)


@dataclass(frozen=True, slots=True)
class Workspace:
    id: int
    slug: str
    name: str
    is_system: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceMembership:
    workspace_id: int
    user_id: int
    role: WorkspaceRole
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceSettings:
    workspace_id: int
    timezone: str
    public_archive_enabled: bool
    downloads_mode: WorkspaceDownloadsMode
    qwen_enabled: bool
    created_at: datetime
    updated_at: datetime
    download_audience: WorkspaceDownloadAudience = "disabled"
    download_variant: WorkspaceDownloadVariant = "watermark"


@dataclass(frozen=True, slots=True)
class WorkspaceChannel:
    workspace_id: int
    kind: WorkspaceChannelKind
    chat_id: int
    url: str | None
    created_at: datetime
    updated_at: datetime


__all__ = (
    "DEFAULT_WORKSPACE_ID",
    "SYSTEM_WORKSPACE_SLUG",
    "WORKSPACE_CHANNEL_KINDS",
    "WORKSPACE_DOWNLOAD_AUDIENCES",
    "WORKSPACE_DOWNLOAD_MODES",
    "WORKSPACE_DOWNLOAD_VARIANTS",
    "WORKSPACE_ROLES",
    "Workspace",
    "WorkspaceChannel",
    "WorkspaceChannelKind",
    "WorkspaceDownloadAudience",
    "WorkspaceDownloadsMode",
    "WorkspaceDownloadVariant",
    "WorkspaceMembership",
    "WorkspaceRole",
    "WorkspaceSettings",
)

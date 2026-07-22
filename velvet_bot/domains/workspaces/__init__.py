from __future__ import annotations

from importlib import import_module
from typing import Final, cast

from velvet_bot.domains.workspaces.models import (
    DEFAULT_WORKSPACE_ID,
    SYSTEM_WORKSPACE_SLUG,
    WORKSPACE_CHANNEL_KINDS,
    WORKSPACE_DOWNLOAD_AUDIENCES,
    WORKSPACE_DOWNLOAD_MODES,
    WORKSPACE_DOWNLOAD_VARIANTS,
    WORKSPACE_ROLES,
    Workspace,
    WorkspaceChannel,
    WorkspaceChannelKind,
    WorkspaceDownloadAudience,
    WorkspaceDownloadsMode,
    WorkspaceDownloadVariant,
    WorkspaceMembership,
    WorkspaceRole,
    WorkspaceSettings,
)

_RUNTIME_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "WorkspaceAccessError": (
        "velvet_bot.domains.workspaces.service",
        "WorkspaceAccessError",
    ),
    "WorkspaceRepository": (
        "velvet_bot.domains.workspaces.repository",
        "WorkspaceRepository",
    ),
    "WorkspaceService": (
        "velvet_bot.domains.workspaces.service",
        "WorkspaceService",
    ),
}

__all__ = (
    "DEFAULT_WORKSPACE_ID",
    "SYSTEM_WORKSPACE_SLUG",
    "WORKSPACE_CHANNEL_KINDS",
    "WORKSPACE_DOWNLOAD_AUDIENCES",
    "WORKSPACE_DOWNLOAD_MODES",
    "WORKSPACE_DOWNLOAD_VARIANTS",
    "WORKSPACE_ROLES",
    "Workspace",
    "WorkspaceAccessError",
    "WorkspaceChannel",
    "WorkspaceChannelKind",
    "WorkspaceDownloadAudience",
    "WorkspaceDownloadsMode",
    "WorkspaceDownloadVariant",
    "WorkspaceMembership",
    "WorkspaceRepository",
    "WorkspaceRole",
    "WorkspaceService",
    "WorkspaceSettings",
)


def __getattr__(name: str) -> object:
    target = _RUNTIME_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = cast(object, getattr(import_module(module_name), attribute_name))
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))

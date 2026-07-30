"""Compatibility aliases for the retired Meow runtime model names."""

from velvet_bot.domains.auf_runtime.models import (
    AufCancellationResult,
    AufProvider,
    AufProviderSnapshot,
    AufRuntimeSettings,
    WorkspaceAufSettings,
)

MeowCancellationResult = AufCancellationResult
MeowProvider = AufProvider
MeowProviderSnapshot = AufProviderSnapshot
MeowRuntimeSettings = AufRuntimeSettings
WorkspaceMeowSettings = WorkspaceAufSettings

__all__ = (
    "MeowCancellationResult",
    "MeowProvider",
    "MeowProviderSnapshot",
    "MeowRuntimeSettings",
    "WorkspaceMeowSettings",
)

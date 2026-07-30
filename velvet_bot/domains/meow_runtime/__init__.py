"""Compatibility package for retired Meow runtime imports.

All implementations live in :mod:`velvet_bot.domains.auf_runtime`.
"""

from velvet_bot.domains.auf_runtime import (
    AufCancellationResult,
    AufProvider,
    AufProviderSnapshot,
    AufRuntimeAccessError,
    AufRuntimeRepository,
    AufRuntimeService,
    AufRuntimeSettings,
    WorkspaceAufSettings,
)

MeowCancellationResult = AufCancellationResult
MeowProvider = AufProvider
MeowProviderSnapshot = AufProviderSnapshot
MeowRuntimeAccessError = AufRuntimeAccessError
MeowRuntimeRepository = AufRuntimeRepository
AufRuntimeService = AufRuntimeService
MeowRuntimeSettings = AufRuntimeSettings
WorkspaceMeowSettings = WorkspaceAufSettings

__all__ = (
    "MeowCancellationResult",
    "MeowProvider",
    "MeowProviderSnapshot",
    "MeowRuntimeAccessError",
    "MeowRuntimeRepository",
    "AufRuntimeService",
    "MeowRuntimeSettings",
    "WorkspaceMeowSettings",
)

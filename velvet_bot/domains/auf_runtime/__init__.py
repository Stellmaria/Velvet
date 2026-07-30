"""Canonical public API for the Auf generation runtime.

The database schema and a few stacked branches still use the historical ``meow``
identifier. New application code must import this package and use ``Auf*`` names;
the old package remains a compatibility boundary until the stacked PRs are merged.
"""

from velvet_bot.domains.meow_runtime import (
    MeowCancellationResult,
    MeowProvider,
    MeowProviderSnapshot,
    MeowRuntimeAccessError,
    MeowRuntimeRepository,
    MeowRuntimeService,
    MeowRuntimeSettings,
    WorkspaceMeowSettings,
)

AufCancellationResult = MeowCancellationResult
AufProvider = MeowProvider
AufProviderSnapshot = MeowProviderSnapshot
AufRuntimeAccessError = MeowRuntimeAccessError
AufRuntimeRepository = MeowRuntimeRepository
AufRuntimeService = MeowRuntimeService
AufRuntimeSettings = MeowRuntimeSettings
WorkspaceAufSettings = WorkspaceMeowSettings

__all__ = (
    "AufCancellationResult",
    "AufProvider",
    "AufProviderSnapshot",
    "AufRuntimeAccessError",
    "AufRuntimeRepository",
    "AufRuntimeService",
    "AufRuntimeSettings",
    "WorkspaceAufSettings",
)

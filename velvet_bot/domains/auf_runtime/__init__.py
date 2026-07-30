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
from velvet_bot.domains.meow_runtime.dispatcher import MeowGenerationDispatcher
from velvet_bot.domains.meow_runtime.queue import ProviderMeowTaskQueueService

# Persistent keys cannot be renamed independently from existing workspace rows and
# already-sent Telegram keyboards. Keep them in one explicit compatibility boundary.
AUF_MODULE_KEY = "meow"
AUF_WORKSPACE_ACTION = "meow"

AufCancellationResult = MeowCancellationResult
AufGenerationDispatcher = MeowGenerationDispatcher
AufProvider = MeowProvider
AufProviderSnapshot = MeowProviderSnapshot
AufRuntimeAccessError = MeowRuntimeAccessError
AufRuntimeRepository = MeowRuntimeRepository
AufRuntimeService = MeowRuntimeService
AufRuntimeSettings = MeowRuntimeSettings
ProviderAufTaskQueueService = ProviderMeowTaskQueueService
WorkspaceAufSettings = WorkspaceMeowSettings

__all__ = (
    "AUF_MODULE_KEY",
    "AUF_WORKSPACE_ACTION",
    "AufCancellationResult",
    "AufGenerationDispatcher",
    "AufProvider",
    "AufProviderSnapshot",
    "AufRuntimeAccessError",
    "AufRuntimeRepository",
    "AufRuntimeService",
    "AufRuntimeSettings",
    "ProviderAufTaskQueueService",
    "WorkspaceAufSettings",
)

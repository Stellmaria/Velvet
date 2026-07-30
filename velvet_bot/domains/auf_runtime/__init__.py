"""Canonical public API for the Auf generation runtime.

The database schema and a few stacked branches still use the historical ``meow``
identifier. New application code imports this package and uses ``Auf*`` names;
the old package is only a compatibility boundary for existing imports and data.
"""

from .dispatcher import AufGenerationDispatcher
from .models import (
    AufCancellationResult,
    AufProvider,
    AufProviderSnapshot,
    AufRuntimeSettings,
    WorkspaceAufSettings,
)
from .queue import ProviderAufTaskQueueService
from .service import AufRuntimeAccessError, AufRuntimeService
from .store import AufRuntimeRepository

# Persistent keys cannot be renamed independently from existing workspace rows and
# already-sent Telegram keyboards. Keep them in one explicit compatibility boundary.
AUF_MODULE_KEY = "meow"
AUF_WORKSPACE_ACTION = "meow"

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

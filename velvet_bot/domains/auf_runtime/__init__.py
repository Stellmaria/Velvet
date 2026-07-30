"""Canonical public API for the Auf generation runtime.

The database schema and application code use canonical ``Auf*`` identifiers.
The old package exists only as a read-only Python import compatibility boundary.
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

AUF_MODULE_KEY = "auf"
AUF_WORKSPACE_ACTION = "auf"
LEGACY_AUF_WORKSPACE_ACTION = "meow"

__all__ = (
    "AUF_MODULE_KEY",
    "AUF_WORKSPACE_ACTION",
    "LEGACY_AUF_WORKSPACE_ACTION",
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

from velvet_bot.domains.telegram_storage import repository as _repository_module
from velvet_bot.domains.telegram_storage.backup_repository import (
    TelegramStorageRepository,
)
from velvet_bot.domains.telegram_storage.models import (
    MigrationSummary,
    StorageCandidate,
    StorageThreadMap,
    TelegramStorageSettings,
)

# `service.py` imports the repository class from the concrete module. Replace that
# export before importing the service so every storage entry point uses the
# codec-independent backup implementation.
_repository_module.TelegramStorageRepository = TelegramStorageRepository

from velvet_bot.domains.telegram_storage.service import (  # noqa: E402
    TelegramStorageMigrationService,
)

__all__ = (
    "MigrationSummary",
    "StorageCandidate",
    "StorageThreadMap",
    "TelegramStorageMigrationService",
    "TelegramStorageRepository",
    "TelegramStorageSettings",
)

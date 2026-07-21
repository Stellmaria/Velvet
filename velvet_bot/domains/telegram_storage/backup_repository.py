from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from velvet_bot.domains.telegram_storage.repository import (
    BackupBackfillItem,
    TelegramStorageRepository as BaseTelegramStorageRepository,
)

logger = logging.getLogger(__name__)


def decode_json_object(value: Any) -> dict[str, Any]:
    """Decode a JSON object regardless of the active asyncpg JSONB codec."""
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            value = bytes(value).decode("utf-8")
        except UnicodeDecodeError:
            logger.warning("Backup validation JSONB contains non-UTF-8 bytes")
            return {}
    if isinstance(value, str):
        if not value.strip():
            return {}
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            logger.warning("Backup validation JSONB contains malformed JSON")
            return {}
        if isinstance(decoded, Mapping):
            return dict(decoded)
        logger.warning(
            "Backup validation JSONB decoded to %s instead of an object",
            type(decoded).__name__,
        )
        return {}
    logger.warning(
        "Backup validation JSONB has unsupported runtime type %s",
        type(value).__name__,
    )
    return {}


class TelegramStorageRepository(BaseTelegramStorageRepository):
    """Storage repository with codec-independent backup metadata decoding."""

    async def list_backup_backfill(
        self,
        backup_dir: Path,
    ) -> list[BackupBackfillItem]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT id, backup_kind, file_path, file_name, sha256,
                       schema_version, validation
                FROM backup_runs
                WHERE status = 'valid'
                  AND file_path IS NOT NULL
                  AND telegram_storage_object_id IS NULL
                ORDER BY started_at, id
                """
            )
        found: list[BackupBackfillItem] = []
        known: set[Path] = set()
        for row in rows:
            path = Path(str(row["file_path"])).expanduser().resolve()
            if not path.is_file():
                continue
            known.add(path)
            found.append(
                BackupBackfillItem(
                    run_id=int(row["id"]),
                    backup_kind=str(row["backup_kind"]),
                    path=path,
                    file_name=str(row["file_name"] or path.name),
                    sha256=str(row["sha256"]) if row["sha256"] else None,
                    schema_version=(
                        str(row["schema_version"])
                        if row["schema_version"]
                        else None
                    ),
                    validation=decode_json_object(row["validation"]),
                )
            )
        if backup_dir.is_dir():
            for path in sorted(backup_dir.glob("*.dump")):
                resolved = path.resolve()
                if resolved in known or not resolved.is_file():
                    continue
                found.append(
                    BackupBackfillItem(
                        run_id=None,
                        backup_kind="untracked",
                        path=resolved,
                        file_name=resolved.name,
                        sha256=None,
                        schema_version=None,
                        validation={},
                    )
                )
        return found


__all__ = (
    "TelegramStorageRepository",
    "decode_json_object",
)

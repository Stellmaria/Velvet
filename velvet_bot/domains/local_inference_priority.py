from __future__ import annotations

import logging
import os

from velvet_bot.database import Database
from velvet_bot.domains.telegram_storage.librarian_models import (
    StorageLibrarianSettings,
)

logger = logging.getLogger(__name__)


def _env_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().casefold()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "да"}


async def storage_librarian_full_archive_has_priority(database: Database) -> bool:
    """Return whether Arthur full-archive work must run before automatic VL work.

    The gate is intentionally phase-oriented rather than based only on current CPU
    activity. It stays closed while a Librarian job is queued/running *or* while an
    eligible Storage object still lacks analysis for the configured analyzer version.
    This prevents VL from slipping into the scheduler's idle gap between bounded
    full-archive cycles.
    """

    if not _env_enabled("STORAGE_LIBRARIAN_AUTO_ENQUEUE", False):
        return False
    if not _env_enabled("STORAGE_LIBRARIAN_AUTO_BACKFILL", False):
        return False

    try:
        settings = StorageLibrarianSettings.from_env()
    except ValueError as error:
        logger.error(
            "Storage Librarian priority gate failed closed on invalid configuration: %s",
            error,
        )
        return True

    if not settings.enabled:
        return False
    if not settings.allowed_kinds:
        logger.error("Storage Librarian priority gate failed closed: empty allowed_kinds")
        return True

    async with database.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT (
                EXISTS (
                    SELECT 1
                    FROM telegram_storage_analysis_jobs AS active_job
                    WHERE active_job.status = 'running'
                       OR (
                           active_job.status = 'queued'
                           AND active_job.attempts < active_job.max_attempts
                       )
                )
                OR EXISTS (
                    SELECT 1
                    FROM telegram_storage_objects AS o
                    LEFT JOIN telegram_storage_analysis AS a
                      ON a.storage_object_id = o.id
                    LEFT JOIN telegram_storage_analysis_jobs AS existing_job
                      ON existing_job.storage_object_id = o.id
                    WHERE o.storage_kind = ANY($1::VARCHAR[])
                      AND o.encrypted = FALSE
                      AND o.size_bytes <= $2::BIGINT
                      AND (
                          a.storage_object_id IS NULL
                          OR a.analyzer_version <> $3::TEXT
                      )
                      AND (
                          existing_job.storage_object_id IS NULL
                          OR (
                              existing_job.status IN ('completed', 'skipped')
                              AND a.storage_object_id IS NOT NULL
                              AND a.analyzer_version <> $3::TEXT
                          )
                      )
                )
            ) AS has_priority_work
            """,
            list(settings.allowed_kinds),
            settings.max_object_bytes,
            settings.analyzer_version,
        )
    if row is None:
        logger.error("Storage Librarian priority gate failed closed: query returned no row")
        return True
    return bool(row["has_priority_work"])


__all__ = ("storage_librarian_full_archive_has_priority",)

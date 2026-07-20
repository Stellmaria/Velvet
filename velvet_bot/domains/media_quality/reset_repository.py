from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.database import Database
from velvet_bot.domains.media_quality.repository import TELEGRAM_BOT_DOWNLOAD_LIMIT


@dataclass(frozen=True, slots=True)
class DuplicateResetResult:
    media_reset: int
    candidates_deleted: int
    fingerprints_deleted: int


class DuplicateResetRepository:
    """Reset visual duplicate analysis without requeueing inaccessible oversized files."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def reset_all(self) -> DuplicateResetResult:
        condition = """
            (
                media_type = 'photo'
                OR (
                    media_type = 'document'
                    AND COALESCE(mime_type, '') LIKE 'image/%'
                )
            )
            AND (
                COALESCE(file_size, 0) <= $1::BIGINT
                OR preview_file_id IS NOT NULL
            )
        """
        async with self._database.acquire() as connection:
            async with connection.transaction():
                candidate_result = await connection.execute(
                    f"""
                    DELETE FROM media_duplicate_candidates
                    WHERE first_media_id IN (
                        SELECT id FROM media_files WHERE {condition}
                    )
                       OR second_media_id IN (
                        SELECT id FROM media_files WHERE {condition}
                    )
                    """,
                    TELEGRAM_BOT_DOWNLOAD_LIMIT,
                )
                fingerprint_result = await connection.execute(
                    f"""
                    DELETE FROM media_visual_fingerprints
                    WHERE media_id IN (
                        SELECT id FROM media_files WHERE {condition}
                    )
                    """,
                    TELEGRAM_BOT_DOWNLOAD_LIMIT,
                )
                media_result = await connection.execute(
                    f"""
                    UPDATE media_files
                    SET visual_scan_status = 'pending',
                        visual_scan_error = NULL,
                        visual_scanned_at = NULL
                    WHERE {condition}
                    """,
                    TELEGRAM_BOT_DOWNLOAD_LIMIT,
                )
        return DuplicateResetResult(
            media_reset=_affected_rows(media_result),
            candidates_deleted=_affected_rows(candidate_result),
            fingerprints_deleted=_affected_rows(fingerprint_result),
        )


def _affected_rows(result: str) -> int:
    try:
        return int(str(result).split()[-1])
    except (TypeError, ValueError, IndexError):
        return 0


__all__ = ("DuplicateResetRepository", "DuplicateResetResult")

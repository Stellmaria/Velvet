from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from velvet_bot.database import Database
from velvet_bot.domains.watermark.models import WatermarkSettings


@dataclass(frozen=True, slots=True)
class ArchiveWatermarkSource:
    media_id: int
    telegram_file_id: str
    file_name: str
    mime_type: str | None
    file_size: int | None
    character_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArchiveWatermarkStorageRecord:
    media_id: int
    chat_id: int
    thread_id: int | None
    message_id: int
    telegram_file_id: str
    file_unique_id: str | None
    file_size: int | None
    sha256: str | None


class PublicArchiveWatermarkRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def get_source(self, media_id: int) -> ArchiveWatermarkSource | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    mf.id,
                    COALESCE(
                        mf.source_telegram_file_id,
                        mf.telegram_file_id
                    ) AS source_file_id,
                    COALESCE(
                        mf.original_file_name,
                        mf.storage_file_name
                    ) AS file_name,
                    mf.mime_type,
                    mf.file_size,
                    ARRAY_REMOVE(
                        ARRAY_AGG(DISTINCT c.name ORDER BY c.name),
                        NULL
                    ) AS character_names
                FROM media_files AS mf
                LEFT JOIN character_media AS cm ON cm.media_id = mf.id
                LEFT JOIN characters AS c ON c.id = cm.character_id
                WHERE mf.id = $1::BIGINT
                  AND (
                        mf.media_type = 'photo'
                        OR COALESCE(mf.mime_type, '') LIKE 'image/%'
                      )
                GROUP BY mf.id
                """,
                int(media_id),
            )
        if row is None:
            return None
        return ArchiveWatermarkSource(
            media_id=int(row["id"]),
            telegram_file_id=str(row["source_file_id"]),
            file_name=str(row["file_name"]),
            mime_type=row["mime_type"],
            file_size=(int(row["file_size"]) if row["file_size"] is not None else None),
            character_names=tuple(str(value) for value in (row["character_names"] or ())),
        )

    async def approve_replacement(
        self,
        *,
        media_id: int,
        telegram_file_id: str,
        telegram_file_unique_id: str | None,
        file_size: int,
        approved_by: int,
        settings: WatermarkSettings,
        storage_chat_id: int,
        storage_thread_id: int | None,
        storage_message_id: int,
        storage_sha256: str,
    ) -> bool:
        template = json.dumps(asdict(settings.normalized()), ensure_ascii=False)
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE media_files
                SET source_telegram_file_id = COALESCE(
                        source_telegram_file_id,
                        telegram_file_id
                    ),
                    telegram_file_id = $2::TEXT,
                    media_type = 'document',
                    mime_type = 'image/png',
                    file_size = $3::BIGINT,
                    preview_file_id = NULL,
                    preview_file_unique_id = NULL,
                    preview_width = NULL,
                    preview_height = NULL,
                    preview_source = NULL,
                    preview_updated_at = NULL,
                    watermark_applied = TRUE,
                    watermark_approved = TRUE,
                    watermark_approved_by = $4::BIGINT,
                    watermark_approved_at = NOW(),
                    watermark_template = $5::JSONB,
                    watermark_storage_chat_id = $6::BIGINT,
                    watermark_storage_thread_id = $7::BIGINT,
                    watermark_storage_message_id = $8::BIGINT,
                    watermark_storage_file_id = $2::TEXT,
                    watermark_storage_file_unique_id = $9::TEXT,
                    watermark_storage_file_size = $3::BIGINT,
                    watermark_storage_sha256 = $10::CHAR(64),
                    watermark_stored_at = NOW(),
                    watermark_local_cleaned_at = NULL
                WHERE id = $1::BIGINT
                """,
                int(media_id),
                telegram_file_id,
                int(file_size),
                int(approved_by),
                template,
                int(storage_chat_id),
                int(storage_thread_id) if storage_thread_id is not None else None,
                int(storage_message_id),
                telegram_file_unique_id,
                storage_sha256,
            )
        return result.endswith("1")

    async def mark_local_cleaned(self, media_id: int) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE media_files
                SET watermark_local_cleaned_at = NOW()
                WHERE id = $1::BIGINT
                  AND watermark_storage_message_id IS NOT NULL
                """,
                int(media_id),
            )

    async def get_storage(
        self,
        media_id: int,
    ) -> ArchiveWatermarkStorageRecord | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    id,
                    watermark_storage_chat_id,
                    watermark_storage_thread_id,
                    watermark_storage_message_id,
                    watermark_storage_file_id,
                    watermark_storage_file_unique_id,
                    watermark_storage_file_size,
                    watermark_storage_sha256
                FROM media_files
                WHERE id = $1::BIGINT
                  AND watermark_storage_chat_id IS NOT NULL
                  AND watermark_storage_message_id IS NOT NULL
                  AND watermark_storage_file_id IS NOT NULL
                """,
                int(media_id),
            )
        if row is None:
            return None
        return ArchiveWatermarkStorageRecord(
            media_id=int(row["id"]),
            chat_id=int(row["watermark_storage_chat_id"]),
            thread_id=(
                int(row["watermark_storage_thread_id"])
                if row["watermark_storage_thread_id"] is not None
                else None
            ),
            message_id=int(row["watermark_storage_message_id"]),
            telegram_file_id=str(row["watermark_storage_file_id"]),
            file_unique_id=(
                str(row["watermark_storage_file_unique_id"])
                if row["watermark_storage_file_unique_id"] is not None
                else None
            ),
            file_size=(
                int(row["watermark_storage_file_size"])
                if row["watermark_storage_file_size"] is not None
                else None
            ),
            sha256=(
                str(row["watermark_storage_sha256"])
                if row["watermark_storage_sha256"] is not None
                else None
            ),
        )


__all__ = (
    "ArchiveWatermarkSource",
    "ArchiveWatermarkStorageRecord",
    "PublicArchiveWatermarkRepository",
)

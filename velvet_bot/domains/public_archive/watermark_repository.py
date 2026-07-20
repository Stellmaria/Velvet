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


class PublicArchiveWatermarkRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def get_source(self, media_id: int) -> ArchiveWatermarkSource | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    id,
                    COALESCE(source_telegram_file_id, telegram_file_id) AS source_file_id,
                    COALESCE(original_file_name, storage_file_name) AS file_name,
                    mime_type,
                    file_size
                FROM media_files
                WHERE id = $1::BIGINT
                  AND (
                        media_type = 'photo'
                        OR COALESCE(mime_type, '') LIKE 'image/%'
                      )
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
        )

    async def approve_replacement(
        self,
        *,
        media_id: int,
        telegram_file_id: str,
        file_size: int,
        approved_by: int,
        settings: WatermarkSettings,
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
                    watermark_template = $5::JSONB
                WHERE id = $1::BIGINT
                """,
                int(media_id),
                telegram_file_id,
                int(file_size),
                int(approved_by),
                template,
            )
        return result.endswith("1")


__all__ = ("ArchiveWatermarkSource", "PublicArchiveWatermarkRepository")

from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.archive.preview_models import PreviewPayload, PreviewRecord


class ArchivePreviewRepository:
    """Persist and retrieve reusable Telegram previews for archive media."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def load(
        self,
        *,
        character_id: int,
        media_id: int,
    ) -> PreviewRecord:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    mf.preview_file_id,
                    mf.preview_file_unique_id,
                    mf.preview_width,
                    mf.preview_height,
                    mf.preview_source,
                    cm.source_chat_id,
                    cm.source_message_id,
                    c.archive_chat_id,
                    cm.archive_message_id
                FROM media_files AS mf
                JOIN character_media AS cm
                  ON cm.media_id = mf.id AND cm.character_id = $1::BIGINT
                JOIN characters AS c ON c.id = cm.character_id
                WHERE mf.id = $2::BIGINT
                """,
                int(character_id),
                int(media_id),
            )
        if row is None:
            return PreviewRecord(None, None, None, None, None, None, None, None, None)
        return PreviewRecord(
            file_id=row["preview_file_id"],
            file_unique_id=row["preview_file_unique_id"],
            width=row["preview_width"],
            height=row["preview_height"],
            source=row["preview_source"],
            source_chat_id=row["source_chat_id"],
            source_message_id=row["source_message_id"],
            archive_chat_id=row["archive_chat_id"],
            archive_message_id=row["archive_message_id"],
        )

    async def save(self, *, media_id: int, preview: PreviewPayload) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE media_files
                SET preview_file_id = $2::TEXT,
                    preview_file_unique_id = COALESCE(
                        $3::TEXT,
                        preview_file_unique_id
                    ),
                    preview_width = COALESCE($4::INTEGER, preview_width),
                    preview_height = COALESCE($5::INTEGER, preview_height),
                    preview_source = $6::TEXT,
                    preview_updated_at = NOW()
                WHERE id = $1::BIGINT
                """,
                int(media_id),
                preview.file_id,
                preview.file_unique_id,
                preview.width,
                preview.height,
                preview.source,
            )


__all__ = ("ArchivePreviewRepository",)

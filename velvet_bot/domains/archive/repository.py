from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.archive.models import ArchivePage, ArchivedMedia, DeletedArchiveItem
from velvet_bot.domains.characters.models import CharacterRecord


class ArchiveRepository:
    """PostgreSQL boundary for character archive browsing and mutations."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def get_page(
        self,
        *,
        character_id: int,
        offset: int,
    ) -> ArchivePage | None:
        safe_offset = max(0, int(offset))
        async with self._database._require_pool().acquire() as connection:
            character_row = await connection.fetchrow(
                """
                SELECT
                    id AS character_id,
                    name AS character_name,
                    created_by,
                    created_in_chat,
                    created_at AS character_created_at,
                    archive_chat_id,
                    archive_thread_id,
                    archive_topic_url
                FROM characters
                WHERE id = $1::BIGINT
                """,
                int(character_id),
            )
            if character_row is None:
                return None

            total = int(
                await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM character_media
                    WHERE character_id = $1::BIGINT
                    """,
                    int(character_id),
                )
                or 0
            )
            character = self._row_to_character(character_row)
            if total == 0:
                return ArchivePage(
                    character=character,
                    media=None,
                    offset=0,
                    total=0,
                )

            normalized_offset = safe_offset % total
            media_row = await connection.fetchrow(
                """
                SELECT
                    mf.id AS media_id,
                    mf.telegram_file_id,
                    mf.media_type,
                    mf.original_file_name,
                    mf.storage_file_name,
                    mf.mime_type,
                    mf.file_size,
                    cm.created_at AS linked_at,
                    cm.prompt_post_url,
                    cm.archive_message_id,
                    cm.is_spoiler
                FROM character_media AS cm
                JOIN media_files AS mf ON mf.id = cm.media_id
                WHERE cm.character_id = $1::BIGINT
                ORDER BY cm.created_at DESC, mf.id DESC
                OFFSET $2::INTEGER
                LIMIT 1
                """,
                int(character_id),
                normalized_offset,
            )

        if media_row is None:
            return ArchivePage(
                character=character,
                media=None,
                offset=0,
                total=0,
            )
        return ArchivePage(
            character=character,
            media=self._row_to_media(media_row),
            offset=normalized_offset,
            total=total,
        )

    async def set_prompt(
        self,
        *,
        character_id: int,
        media_id: int,
        prompt_post_url: str | None,
    ) -> bool:
        async with self._database._require_pool().acquire() as connection:
            updated = await connection.fetchval(
                """
                UPDATE character_media
                SET prompt_post_url = $3::TEXT
                WHERE character_id = $1::BIGINT
                  AND media_id = $2::BIGINT
                RETURNING 1
                """,
                int(character_id),
                int(media_id),
                prompt_post_url,
            )
        return updated is not None

    async def set_spoiler(
        self,
        *,
        character_id: int,
        media_id: int,
        is_spoiler: bool,
    ) -> bool:
        async with self._database._require_pool().acquire() as connection:
            updated = await connection.fetchval(
                """
                UPDATE character_media
                SET is_spoiler = $3::BOOLEAN
                WHERE character_id = $1::BIGINT
                  AND media_id = $2::BIGINT
                RETURNING 1
                """,
                int(character_id),
                int(media_id),
                bool(is_spoiler),
            )
        return updated is not None

    async def toggle_spoiler(
        self,
        *,
        character_id: int,
        media_id: int,
    ) -> bool | None:
        async with self._database._require_pool().acquire() as connection:
            value = await connection.fetchval(
                """
                UPDATE character_media
                SET is_spoiler = NOT is_spoiler
                WHERE character_id = $1::BIGINT
                  AND media_id = $2::BIGINT
                RETURNING is_spoiler
                """,
                int(character_id),
                int(media_id),
            )
        return bool(value) if value is not None else None

    async def delete_item(
        self,
        *,
        character_id: int,
        media_id: int,
    ) -> DeletedArchiveItem | None:
        async with self._database._require_pool().acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT
                        c.id AS character_id,
                        c.name AS character_name,
                        c.created_by,
                        c.created_in_chat,
                        c.created_at AS character_created_at,
                        c.archive_chat_id,
                        c.archive_thread_id,
                        c.archive_topic_url,
                        mf.id AS media_id,
                        mf.telegram_file_id,
                        mf.media_type,
                        mf.original_file_name,
                        mf.storage_file_name,
                        mf.mime_type,
                        mf.file_size,
                        cm.created_at AS linked_at,
                        cm.prompt_post_url,
                        cm.archive_message_id,
                        cm.is_spoiler
                    FROM character_media AS cm
                    JOIN characters AS c ON c.id = cm.character_id
                    JOIN media_files AS mf ON mf.id = cm.media_id
                    WHERE cm.character_id = $1::BIGINT
                      AND cm.media_id = $2::BIGINT
                    FOR UPDATE OF cm
                    """,
                    int(character_id),
                    int(media_id),
                )
                if row is None:
                    return None

                await connection.execute(
                    """
                    DELETE FROM character_media
                    WHERE character_id = $1::BIGINT
                      AND media_id = $2::BIGINT
                    """,
                    int(character_id),
                    int(media_id),
                )
                remaining_links = int(
                    await connection.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM character_media
                        WHERE media_id = $1::BIGINT
                        """,
                        int(media_id),
                    )
                    or 0
                )
                orphan_media_removed = remaining_links == 0
                if orphan_media_removed:
                    await connection.execute(
                        "DELETE FROM media_files WHERE id = $1::BIGINT",
                        int(media_id),
                    )
                remaining_total = int(
                    await connection.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM character_media
                        WHERE character_id = $1::BIGINT
                        """,
                        int(character_id),
                    )
                    or 0
                )

        return DeletedArchiveItem(
            character=self._row_to_character(row),
            media=self._row_to_media(row),
            remaining_total=remaining_total,
            orphan_media_removed=orphan_media_removed,
        )

    @staticmethod
    def _row_to_character(row) -> CharacterRecord:
        return CharacterRecord(
            id=int(row["character_id"]),
            name=str(row["character_name"]),
            created_by=row["created_by"],
            created_in_chat=row["created_in_chat"],
            created_at=row["character_created_at"],
            archive_chat_id=row["archive_chat_id"],
            archive_thread_id=row["archive_thread_id"],
            archive_topic_url=row["archive_topic_url"],
        )

    @staticmethod
    def _row_to_media(row) -> ArchivedMedia:
        return ArchivedMedia(
            id=int(row["media_id"]),
            telegram_file_id=str(row["telegram_file_id"]),
            media_type=str(row["media_type"]),
            original_file_name=row["original_file_name"],
            storage_file_name=str(row["storage_file_name"]),
            mime_type=row["mime_type"],
            file_size=(int(row["file_size"]) if row["file_size"] is not None else None),
            linked_at=row["linked_at"],
            prompt_post_url=row["prompt_post_url"],
            archive_message_id=(
                int(row["archive_message_id"])
                if row["archive_message_id"] is not None
                else None
            ),
            is_spoiler=bool(row["is_spoiler"]),
        )


__all__ = ("ArchiveRepository",)

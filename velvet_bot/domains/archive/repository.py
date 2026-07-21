from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.archive.models import ArchivePage, ArchivedMedia, DeletedArchiveItem
from velvet_bot.domains.characters.models import CharacterRecord
from velvet_bot.domains.public_archive.visibility import public_media_visibility_sql
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID


class ArchiveRepository:
    """PostgreSQL boundary for character archive browsing and mutations."""

    def __init__(
        self,
        database: Database,
        *,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> None:
        self._database = database
        self._workspace_id = int(workspace_id)

    async def get_page(
        self,
        *,
        character_id: int,
        offset: int,
        public_only: bool = False,
        include_adult_restricted: bool = False,
        include_oversized_images: bool = False,
    ) -> ArchivePage | None:
        safe_offset = max(0, int(offset))
        visibility_sql = public_media_visibility_sql(
            include_adult_restricted=include_adult_restricted,
            include_oversized_images=include_oversized_images,
        )
        async with self._database.acquire() as connection:
            character_row = await connection.fetchrow(
                """
                SELECT
                    id AS character_id,
                    workspace_id,
                    name AS character_name,
                    created_by,
                    created_in_chat,
                    created_at AS character_created_at,
                    archive_chat_id,
                    archive_thread_id,
                    archive_topic_url
                FROM characters
                WHERE id = $1::BIGINT
                  AND workspace_id = $2::BIGINT
                """,
                int(character_id),
                self._workspace_id,
            )
            if character_row is None:
                return None

            total = int(
                await connection.fetchval(
                    f"""
                    SELECT COUNT(*)
                    FROM character_media AS cm
                    JOIN media_files AS mf ON mf.id = cm.media_id
                    WHERE cm.character_id = $1::BIGINT
                      AND (
                            $2::BOOLEAN = FALSE
                            OR ({visibility_sql})
                          )
                    """,
                    int(character_id),
                    bool(public_only),
                )
                or 0
            )
            character = self._row_to_character(character_row)
            if total == 0:
                return ArchivePage(character=character, media=None, offset=0, total=0)

            normalized_offset = safe_offset % total
            media_row = await connection.fetchrow(
                f"""
                SELECT
                    mf.id AS media_id,
                    mf.telegram_file_id,
                    mf.media_type,
                    mf.original_file_name,
                    mf.storage_file_name,
                    mf.mime_type,
                    mf.file_size,
                    cm.created_at AS linked_at,
                    CASE
                        WHEN ms.id IS NOT NULL THEN ms.prompt_post_url
                        ELSE cm.prompt_post_url
                    END AS prompt_post_url,
                    cm.archive_message_id,
                    cm.is_spoiler,
                    cm.is_public,
                    cm.requires_adult_channel,
                    ms.id AS media_set_id,
                    ms.title AS media_set_title
                FROM character_media AS cm
                JOIN media_files AS mf ON mf.id = cm.media_id
                LEFT JOIN media_sets AS ms ON ms.id = mf.media_set_id
                WHERE cm.character_id = $1::BIGINT
                  AND (
                        $2::BOOLEAN = FALSE
                        OR ({visibility_sql})
                      )
                ORDER BY cm.created_at DESC, mf.id DESC
                OFFSET $3::INTEGER
                LIMIT 1
                """,
                int(character_id),
                bool(public_only),
                normalized_offset,
            )

        if media_row is None:
            return ArchivePage(character=character, media=None, offset=0, total=0)
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
        async with self._database.acquire() as connection:
            updated = await connection.fetchval(
                """
                UPDATE character_media AS cm
                SET prompt_post_url = $3::TEXT
                WHERE cm.character_id = $1::BIGINT
                  AND cm.media_id = $2::BIGINT
                  AND EXISTS (
                        SELECT 1
                        FROM characters AS c
                        WHERE c.id = cm.character_id
                          AND c.workspace_id = $4::BIGINT
                      )
                RETURNING 1
                """,
                int(character_id),
                int(media_id),
                prompt_post_url,
                self._workspace_id,
            )
        return updated is not None

    async def set_spoiler(
        self,
        *,
        character_id: int,
        media_id: int,
        is_spoiler: bool,
    ) -> bool:
        async with self._database.acquire() as connection:
            updated = await connection.fetchval(
                """
                UPDATE character_media AS cm
                SET is_spoiler = $3::BOOLEAN
                WHERE cm.character_id = $1::BIGINT
                  AND cm.media_id = $2::BIGINT
                  AND EXISTS (
                        SELECT 1
                        FROM characters AS c
                        WHERE c.id = cm.character_id
                          AND c.workspace_id = $4::BIGINT
                      )
                RETURNING 1
                """,
                int(character_id),
                int(media_id),
                bool(is_spoiler),
                self._workspace_id,
            )
        return updated is not None

    async def toggle_spoiler(
        self,
        *,
        character_id: int,
        media_id: int,
    ) -> bool | None:
        return await self._toggle_boolean(
            character_id=character_id,
            media_id=media_id,
            column="is_spoiler",
        )

    async def toggle_public_visibility(
        self,
        *,
        character_id: int,
        media_id: int,
    ) -> bool | None:
        return await self._toggle_boolean(
            character_id=character_id,
            media_id=media_id,
            column="is_public",
        )

    async def toggle_adult_requirement(
        self,
        *,
        character_id: int,
        media_id: int,
    ) -> bool | None:
        return await self._toggle_boolean(
            character_id=character_id,
            media_id=media_id,
            column="requires_adult_channel",
        )

    async def _toggle_boolean(
        self,
        *,
        character_id: int,
        media_id: int,
        column: str,
    ) -> bool | None:
        allowed = {"is_spoiler", "is_public", "requires_adult_channel"}
        if column not in allowed:
            raise ValueError("Неизвестный флаг медиа.")
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                f"""
                UPDATE character_media AS cm
                SET {column} = NOT {column}
                WHERE cm.character_id = $1::BIGINT
                  AND cm.media_id = $2::BIGINT
                  AND EXISTS (
                        SELECT 1
                        FROM characters AS c
                        WHERE c.id = cm.character_id
                          AND c.workspace_id = $3::BIGINT
                      )
                RETURNING {column}
                """,
                int(character_id),
                int(media_id),
                self._workspace_id,
            )
        return bool(value) if value is not None else None

    async def delete_item(
        self,
        *,
        character_id: int,
        media_id: int,
    ) -> DeletedArchiveItem | None:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT
                        c.id AS character_id,
                        c.workspace_id,
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
                        CASE
                            WHEN ms.id IS NOT NULL THEN ms.prompt_post_url
                            ELSE cm.prompt_post_url
                        END AS prompt_post_url,
                        cm.archive_message_id,
                        cm.is_spoiler,
                        cm.is_public,
                        cm.requires_adult_channel,
                        ms.id AS media_set_id,
                        ms.title AS media_set_title
                    FROM character_media AS cm
                    JOIN characters AS c ON c.id = cm.character_id
                    JOIN media_files AS mf ON mf.id = cm.media_id
                    LEFT JOIN media_sets AS ms ON ms.id = mf.media_set_id
                    WHERE cm.character_id = $1::BIGINT
                      AND cm.media_id = $2::BIGINT
                      AND c.workspace_id = $3::BIGINT
                    FOR UPDATE OF cm
                    """,
                    int(character_id),
                    int(media_id),
                    self._workspace_id,
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
                        "SELECT COUNT(*) FROM character_media WHERE media_id = $1::BIGINT",
                        int(media_id),
                    )
                    or 0
                )
                orphan_media_removed = remaining_links == 0
                if orphan_media_removed:
                    media_set_id = row["media_set_id"]
                    await connection.execute(
                        "DELETE FROM media_files WHERE id = $1::BIGINT",
                        int(media_id),
                    )
                    if media_set_id is not None:
                        await connection.execute(
                            """
                            DELETE FROM media_sets AS media_set
                            WHERE media_set.id = $1::BIGINT
                              AND NOT EXISTS (
                                SELECT 1 FROM media_files
                                WHERE media_set_id = media_set.id
                              )
                            """,
                            int(media_set_id),
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
            workspace_id=int(row["workspace_id"]),
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
            is_public=bool(row["is_public"]),
            requires_adult_channel=bool(row["requires_adult_channel"]),
            media_set_id=(
                int(row["media_set_id"])
                if row["media_set_id"] is not None
                else None
            ),
            media_set_title=row["media_set_title"],
        )


__all__ = ("ArchiveRepository",)

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

from velvet_bot.database import Character, Database


@dataclass(frozen=True, slots=True)
class ArchivedMedia:
    id: int
    telegram_file_id: str
    media_type: str
    original_file_name: str | None
    storage_file_name: str
    mime_type: str | None
    file_size: int | None
    linked_at: datetime
    archive_message_id: int | None = None

    @property
    def display_file_name(self) -> str:
        return self.original_file_name or self.storage_file_name

    @property
    def is_image_document(self) -> bool:
        return self.media_type == "document" and (self.mime_type or "").startswith(
            "image/"
        )


@dataclass(frozen=True, slots=True)
class ArchivePage:
    character: Character
    media: ArchivedMedia | None
    offset: int
    total: int


@dataclass(frozen=True, slots=True)
class DeletedArchiveItem:
    character: Character
    media: ArchivedMedia
    remaining_total: int
    orphan_media_removed: bool


def _row_to_character(row: asyncpg.Record) -> Character:
    return Character(
        id=int(row["character_id"]),
        name=str(row["character_name"]),
        created_by=row["created_by"],
        created_in_chat=row["created_in_chat"],
        created_at=row["character_created_at"],
        archive_chat_id=row["archive_chat_id"],
        archive_thread_id=row["archive_thread_id"],
        archive_topic_url=row["archive_topic_url"],
    )


def _row_to_media(row: asyncpg.Record) -> ArchivedMedia:
    return ArchivedMedia(
        id=int(row["media_id"]),
        telegram_file_id=str(row["telegram_file_id"]),
        media_type=str(row["media_type"]),
        original_file_name=row["original_file_name"],
        storage_file_name=str(row["storage_file_name"]),
        mime_type=row["mime_type"],
        file_size=row["file_size"],
        linked_at=row["linked_at"],
        archive_message_id=(
            int(row["archive_message_id"])
            if row["archive_message_id"] is not None
            else None
        ),
    )


async def get_archive_page(
    database: Database,
    character_id: int,
    offset: int,
) -> ArchivePage | None:
    """Return one archived media item and the total count for a character."""
    safe_offset = max(0, offset)

    async with database._require_pool().acquire() as connection:
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
            WHERE id = $1
            """,
            character_id,
        )
        if character_row is None:
            return None

        total = int(
            await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM character_media
                WHERE character_id = $1
                """,
                character_id,
            )
            or 0
        )

        character = _row_to_character(character_row)
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
                cm.archive_message_id
            FROM character_media AS cm
            JOIN media_files AS mf ON mf.id = cm.media_id
            WHERE cm.character_id = $1
            ORDER BY cm.created_at DESC, mf.id DESC
            OFFSET $2
            LIMIT 1
            """,
            character_id,
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
        media=_row_to_media(media_row),
        offset=normalized_offset,
        total=total,
    )


async def delete_archive_item(
    database: Database,
    character_id: int,
    media_id: int,
) -> DeletedArchiveItem | None:
    """Remove a media link from a character and prune an orphaned media row."""
    async with database._require_pool().acquire() as connection:
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
                    cm.archive_message_id
                FROM character_media AS cm
                JOIN characters AS c ON c.id = cm.character_id
                JOIN media_files AS mf ON mf.id = cm.media_id
                WHERE cm.character_id = $1 AND cm.media_id = $2
                FOR UPDATE OF cm
                """,
                character_id,
                media_id,
            )
            if row is None:
                return None

            await connection.execute(
                """
                DELETE FROM character_media
                WHERE character_id = $1 AND media_id = $2
                """,
                character_id,
                media_id,
            )

            remaining_links = int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM character_media WHERE media_id = $1",
                    media_id,
                )
                or 0
            )
            orphan_media_removed = remaining_links == 0
            if orphan_media_removed:
                await connection.execute(
                    "DELETE FROM media_files WHERE id = $1",
                    media_id,
                )

            remaining_total = int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM character_media WHERE character_id = $1",
                    character_id,
                )
                or 0
            )

    return DeletedArchiveItem(
        character=_row_to_character(row),
        media=_row_to_media(row),
        remaining_total=remaining_total,
        orphan_media_removed=orphan_media_removed,
    )

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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

    @property
    def display_file_name(self) -> str:
        return self.original_file_name or self.storage_file_name


@dataclass(frozen=True, slots=True)
class ArchivePage:
    character: Character
    media: ArchivedMedia | None
    offset: int
    total: int


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
                id,
                name,
                created_by,
                created_in_chat,
                created_at,
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

        character = Character(
            id=int(character_row["id"]),
            name=str(character_row["name"]),
            created_by=character_row["created_by"],
            created_in_chat=character_row["created_in_chat"],
            created_at=character_row["created_at"],
            archive_chat_id=character_row["archive_chat_id"],
            archive_thread_id=character_row["archive_thread_id"],
            archive_topic_url=character_row["archive_topic_url"],
        )

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
                mf.id,
                mf.telegram_file_id,
                mf.media_type,
                mf.original_file_name,
                mf.storage_file_name,
                mf.mime_type,
                mf.file_size,
                cm.created_at AS linked_at
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
        media=ArchivedMedia(
            id=int(media_row["id"]),
            telegram_file_id=str(media_row["telegram_file_id"]),
            media_type=str(media_row["media_type"]),
            original_file_name=media_row["original_file_name"],
            storage_file_name=str(media_row["storage_file_name"]),
            mime_type=media_row["mime_type"],
            file_size=media_row["file_size"],
            linked_at=media_row["linked_at"],
        ),
        offset=normalized_offset,
        total=total,
    )

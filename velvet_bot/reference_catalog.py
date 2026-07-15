from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aiogram.types import PhotoSize

from velvet_bot.database import Character, Database


@dataclass(frozen=True, slots=True)
class CharacterReference:
    id: int
    character_id: int
    telegram_file_id: str
    telegram_file_unique_id: str
    added_by: int | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ReferencePage:
    character: Character
    reference: CharacterReference | None
    offset: int
    total: int


@dataclass(frozen=True, slots=True)
class AddReferenceResult:
    reference: CharacterReference
    created: bool
    total: int


@dataclass(frozen=True, slots=True)
class DeleteReferenceResult:
    reference: CharacterReference | None
    total: int


_REFERENCE_SELECT = """
    id AS reference_id,
    character_id,
    telegram_file_id,
    telegram_file_unique_id,
    added_by,
    created_at AS reference_created_at
"""


def _row_to_character(row) -> Character:
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


def _row_to_reference(row) -> CharacterReference:
    return CharacterReference(
        id=int(row["reference_id"]),
        character_id=int(row["character_id"]),
        telegram_file_id=str(row["telegram_file_id"]),
        telegram_file_unique_id=str(row["telegram_file_unique_id"]),
        added_by=row["added_by"],
        created_at=row["reference_created_at"],
    )


async def add_character_reference(
    database: Database,
    character: Character,
    photo: PhotoSize,
    *,
    added_by: int | None,
) -> AddReferenceResult:
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            row = await connection.fetchrow(
                f"""
                INSERT INTO character_references (
                    character_id,
                    telegram_file_id,
                    telegram_file_unique_id,
                    added_by
                )
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (character_id, telegram_file_unique_id) DO NOTHING
                RETURNING {_REFERENCE_SELECT}
                """,
                character.id,
                photo.file_id,
                photo.file_unique_id,
                added_by,
            )
            created = row is not None
            if row is None:
                row = await connection.fetchrow(
                    f"""
                    UPDATE character_references
                    SET telegram_file_id = $3
                    WHERE character_id = $1
                      AND telegram_file_unique_id = $2
                    RETURNING {_REFERENCE_SELECT}
                    """,
                    character.id,
                    photo.file_unique_id,
                    photo.file_id,
                )
            if row is None:
                raise RuntimeError("Не удалось сохранить референс персонажа.")

            total = int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM character_references WHERE character_id = $1",
                    character.id,
                )
                or 0
            )

    return AddReferenceResult(
        reference=_row_to_reference(row),
        created=created,
        total=total,
    )


async def delete_character_reference(
    database: Database,
    character_id: int,
    reference_id: int,
) -> DeleteReferenceResult:
    """Delete one exact reference and return the remaining count."""
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            row = await connection.fetchrow(
                f"""
                DELETE FROM character_references
                WHERE id = $1
                  AND character_id = $2
                RETURNING {_REFERENCE_SELECT}
                """,
                reference_id,
                character_id,
            )
            total = int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM character_references WHERE character_id = $1",
                    character_id,
                )
                or 0
            )

    return DeleteReferenceResult(
        reference=_row_to_reference(row) if row is not None else None,
        total=total,
    )


async def count_character_references(database: Database, character_id: int) -> int:
    async with database._require_pool().acquire() as connection:
        value = await connection.fetchval(
            "SELECT COUNT(*) FROM character_references WHERE character_id = $1",
            character_id,
        )
    return int(value or 0)


async def list_character_references(
    database: Database,
    character_id: int,
    *,
    limit: int = 50,
) -> list[CharacterReference]:
    safe_limit = max(1, min(limit, 50))
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            f"""
            SELECT {_REFERENCE_SELECT}
            FROM character_references
            WHERE character_id = $1
            ORDER BY created_at, id
            LIMIT $2
            """,
            character_id,
            safe_limit,
        )
    return [_row_to_reference(row) for row in rows]


async def get_reference_page(
    database: Database,
    character_id: int,
    offset: int,
) -> ReferencePage | None:
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
                "SELECT COUNT(*) FROM character_references WHERE character_id = $1",
                character_id,
            )
            or 0
        )
        character = _row_to_character(character_row)
        if total == 0:
            return ReferencePage(
                character=character,
                reference=None,
                offset=0,
                total=0,
            )

        normalized_offset = safe_offset % total
        reference_row = await connection.fetchrow(
            f"""
            SELECT {_REFERENCE_SELECT}
            FROM character_references
            WHERE character_id = $1
            ORDER BY created_at, id
            OFFSET $2
            LIMIT 1
            """,
            character_id,
            normalized_offset,
        )

    return ReferencePage(
        character=character,
        reference=(
            _row_to_reference(reference_row)
            if reference_row is not None
            else None
        ),
        offset=normalized_offset,
        total=total,
    )

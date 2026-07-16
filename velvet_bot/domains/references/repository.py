from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.characters.models import CharacterRecord
from velvet_bot.domains.references.models import (
    AddReferenceResult,
    CharacterReference,
    DeleteReferenceResult,
    ReferenceMediaPayload,
    ReferencePage,
)

_REFERENCE_SELECT = """
    id AS reference_id,
    character_id,
    telegram_file_id,
    telegram_file_unique_id,
    added_by,
    created_at AS reference_created_at
"""


class ReferenceRepository:
    """PostgreSQL boundary for character reference images."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def add(
        self,
        *,
        character_id: int,
        media: ReferenceMediaPayload,
        added_by: int | None,
    ) -> AddReferenceResult:
        async with self._database._require_pool().acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    f"""
                    INSERT INTO character_references (
                        character_id,
                        telegram_file_id,
                        telegram_file_unique_id,
                        added_by
                    )
                    VALUES ($1::BIGINT, $2::TEXT, $3::TEXT, $4::BIGINT)
                    ON CONFLICT (character_id, telegram_file_unique_id) DO NOTHING
                    RETURNING {_REFERENCE_SELECT}
                    """,
                    int(character_id),
                    media.telegram_file_id,
                    media.telegram_file_unique_id,
                    added_by,
                )
                created = row is not None
                if row is None:
                    row = await connection.fetchrow(
                        f"""
                        UPDATE character_references
                        SET telegram_file_id = $3::TEXT
                        WHERE character_id = $1::BIGINT
                          AND telegram_file_unique_id = $2::TEXT
                        RETURNING {_REFERENCE_SELECT}
                        """,
                        int(character_id),
                        media.telegram_file_unique_id,
                        media.telegram_file_id,
                    )
                if row is None:
                    raise RuntimeError("Не удалось сохранить референс персонажа.")
                total = int(
                    await connection.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM character_references
                        WHERE character_id = $1::BIGINT
                        """,
                        int(character_id),
                    )
                    or 0
                )
        return AddReferenceResult(
            reference=self._row_to_reference(row),
            created=created,
            total=total,
        )

    async def delete(
        self,
        *,
        character_id: int,
        reference_id: int,
    ) -> DeleteReferenceResult:
        async with self._database._require_pool().acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    f"""
                    DELETE FROM character_references
                    WHERE id = $1::BIGINT
                      AND character_id = $2::BIGINT
                    RETURNING {_REFERENCE_SELECT}
                    """,
                    int(reference_id),
                    int(character_id),
                )
                total = int(
                    await connection.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM character_references
                        WHERE character_id = $1::BIGINT
                        """,
                        int(character_id),
                    )
                    or 0
                )
        return DeleteReferenceResult(
            reference=(self._row_to_reference(row) if row is not None else None),
            total=total,
        )

    async def count(self, character_id: int) -> int:
        async with self._database._require_pool().acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM character_references
                WHERE character_id = $1::BIGINT
                """,
                int(character_id),
            )
        return int(value or 0)

    async def list(
        self,
        character_id: int,
        *,
        limit: int = 50,
    ) -> list[CharacterReference]:
        safe_limit = max(1, min(int(limit), 50))
        async with self._database._require_pool().acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT {_REFERENCE_SELECT}
                FROM character_references
                WHERE character_id = $1::BIGINT
                ORDER BY created_at, id
                LIMIT $2::INTEGER
                """,
                int(character_id),
                safe_limit,
            )
        return [self._row_to_reference(row) for row in rows]

    async def get_page(
        self,
        character_id: int,
        offset: int,
    ) -> ReferencePage | None:
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
                    FROM character_references
                    WHERE character_id = $1::BIGINT
                    """,
                    int(character_id),
                )
                or 0
            )
            character = self._row_to_character(character_row)
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
                WHERE character_id = $1::BIGINT
                ORDER BY created_at, id
                OFFSET $2::INTEGER
                LIMIT 1
                """,
                int(character_id),
                normalized_offset,
            )
        return ReferencePage(
            character=character,
            reference=(
                self._row_to_reference(reference_row)
                if reference_row is not None
                else None
            ),
            offset=normalized_offset,
            total=total,
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
    def _row_to_reference(row) -> CharacterReference:
        return CharacterReference(
            id=int(row["reference_id"]),
            character_id=int(row["character_id"]),
            telegram_file_id=str(row["telegram_file_id"]),
            telegram_file_unique_id=str(row["telegram_file_unique_id"]),
            added_by=row["added_by"],
            created_at=row["reference_created_at"],
        )


__all__ = ("ReferenceRepository",)

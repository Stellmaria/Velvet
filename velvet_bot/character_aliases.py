from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from velvet_bot.database import Database


@dataclass(frozen=True, slots=True)
class CharacterAlias:
    id: int
    character_id: int
    character_name: str
    alias: str
    normalized_alias: str
    source: str


def normalize_character_alias(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


async def load_character_alias_map(connection) -> dict[str, tuple[int, str]]:
    rows = await connection.fetch(
        """
        SELECT a.normalized_alias, c.id AS character_id, c.name
        FROM character_aliases AS a
        JOIN characters AS c ON c.id = a.character_id
        ORDER BY a.id
        """
    )
    return {
        str(row["normalized_alias"]): (
            int(row["character_id"]),
            str(row["name"]),
        )
        for row in rows
    }


async def ensure_name_aliases(database: Database) -> int:
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch("SELECT id, name FROM characters ORDER BY id")
        created = 0
        for row in rows:
            normalized = normalize_character_alias(str(row["name"]))
            if not normalized:
                continue
            result = await connection.execute(
                """
                INSERT INTO character_aliases (
                    character_id, alias, normalized_alias, source
                )
                VALUES ($1, $2, $3, 'name')
                ON CONFLICT (normalized_alias) DO NOTHING
                """,
                int(row["id"]),
                str(row["name"]),
                normalized,
            )
            if result == "INSERT 0 1":
                created += 1
    return created


async def list_character_aliases(
    database: Database,
    *,
    character_id: int,
) -> list[CharacterAlias]:
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                a.id,
                a.character_id,
                c.name AS character_name,
                a.alias,
                a.normalized_alias,
                a.source
            FROM character_aliases AS a
            JOIN characters AS c ON c.id = a.character_id
            WHERE a.character_id = $1
            ORDER BY CASE a.source WHEN 'name' THEN 0 ELSE 1 END, a.alias
            """,
            character_id,
        )
    return [
        CharacterAlias(
            id=int(row["id"]),
            character_id=int(row["character_id"]),
            character_name=str(row["character_name"]),
            alias=str(row["alias"]),
            normalized_alias=str(row["normalized_alias"]),
            source=str(row["source"]),
        )
        for row in rows
    ]


async def add_character_alias(
    database: Database,
    *,
    character_id: int,
    alias: str,
    created_by: int | None,
) -> CharacterAlias:
    cleaned = " ".join(unicodedata.normalize("NFKC", alias).split())
    normalized = normalize_character_alias(cleaned)
    if not cleaned or not normalized:
        raise ValueError("Алиас не может быть пустым.")
    if len(cleaned) > 64:
        raise ValueError("Алиас не должен быть длиннее 64 символов.")

    async with database._require_pool().acquire() as connection:
        character = await connection.fetchrow(
            "SELECT id, name FROM characters WHERE id = $1",
            character_id,
        )
        if character is None:
            raise ValueError("Персонаж не найден.")
        conflict = await connection.fetchrow(
            """
            SELECT c.name, a.character_id
            FROM character_aliases AS a
            JOIN characters AS c ON c.id = a.character_id
            WHERE a.normalized_alias = $1
            """,
            normalized,
        )
        if conflict is not None and int(conflict["character_id"]) != character_id:
            raise ValueError(
                f"Этот алиас уже принадлежит персонажу {conflict['name']}."
            )
        row = await connection.fetchrow(
            """
            INSERT INTO character_aliases (
                character_id,
                alias,
                normalized_alias,
                source,
                created_by,
                updated_at
            )
            VALUES ($1, $2, $3, 'manual', $4, NOW())
            ON CONFLICT (character_id, normalized_alias) DO UPDATE
            SET alias = EXCLUDED.alias,
                updated_at = NOW()
            RETURNING id, character_id, alias, normalized_alias, source
            """,
            character_id,
            cleaned,
            normalized,
            created_by,
        )
        if row is None:
            raise RuntimeError("Не удалось сохранить алиас.")

        await connection.execute(
            """
            UPDATE channel_post_hashtags
            SET character_id = $1,
                is_character = TRUE
            WHERE character_id IS NULL
              AND REGEXP_REPLACE(
                    LOWER(normalized_hashtag),
                    '[^[:alnum:]]+',
                    '',
                    'g'
                  ) = $2
            """,
            character_id,
            normalized,
        )

    return CharacterAlias(
        id=int(row["id"]),
        character_id=int(row["character_id"]),
        character_name=str(character["name"]),
        alias=str(row["alias"]),
        normalized_alias=str(row["normalized_alias"]),
        source=str(row["source"]),
    )


async def delete_character_alias(
    database: Database,
    *,
    character_id: int,
    alias: str,
) -> bool:
    normalized = normalize_character_alias(alias)
    if not normalized:
        return False
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            DELETE FROM character_aliases
            WHERE character_id = $1
              AND normalized_alias = $2
              AND source <> 'name'
            RETURNING id
            """,
            character_id,
            normalized,
        )
        if row is None:
            return False
        await connection.execute(
            """
            UPDATE channel_post_hashtags AS h
            SET character_id = NULL,
                is_character = FALSE
            WHERE h.character_id = $1
              AND REGEXP_REPLACE(
                    LOWER(h.normalized_hashtag),
                    '[^[:alnum:]]+',
                    '',
                    'g'
                  ) = $2
              AND NOT EXISTS (
                    SELECT 1
                    FROM character_aliases AS a
                    WHERE a.character_id = $1
                      AND a.normalized_alias = $2
                  )
            """,
            character_id,
            normalized,
        )
    return True


async def rebuild_hashtag_character_links(database: Database) -> tuple[int, int]:
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                "UPDATE channel_post_hashtags SET character_id = NULL, is_character = FALSE"
            )
            rows = await connection.fetch(
                """
                SELECT normalized_alias, character_id
                FROM character_aliases
                ORDER BY id
                """
            )
            matched = 0
            for row in rows:
                result = await connection.execute(
                    """
                    UPDATE channel_post_hashtags
                    SET character_id = $1,
                        is_character = TRUE
                    WHERE character_id IS NULL
                      AND REGEXP_REPLACE(
                            LOWER(normalized_hashtag),
                            '[^[:alnum:]]+',
                            '',
                            'g'
                          ) = $2
                    """,
                    int(row["character_id"]),
                    str(row["normalized_alias"]),
                )
                matched += int(result.rsplit(" ", 1)[-1])
            total = int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM channel_post_hashtags"
                )
                or 0
            )
    return matched, total

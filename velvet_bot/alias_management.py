from __future__ import annotations

from velvet_bot.character_aliases import (
    CharacterAlias,
    delete_character_alias,
    list_character_aliases,
)
from velvet_bot.database import Database


async def get_character_alias_by_id(
    database: Database,
    *,
    alias_id: int,
) -> CharacterAlias | None:
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
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
            WHERE a.id = $1
            """,
            alias_id,
        )
    if row is None:
        return None
    return CharacterAlias(
        id=int(row["id"]),
        character_id=int(row["character_id"]),
        character_name=str(row["character_name"]),
        alias=str(row["alias"]),
        normalized_alias=str(row["normalized_alias"]),
        source=str(row["source"]),
    )


async def delete_character_alias_by_id(
    database: Database,
    *,
    alias_id: int,
) -> CharacterAlias | None:
    item = await get_character_alias_by_id(database, alias_id=alias_id)
    if item is None or item.source == "name":
        return None
    deleted = await delete_character_alias(
        database,
        character_id=item.character_id,
        alias=item.alias,
    )
    return item if deleted else None


async def get_character_alias_summary(
    database: Database,
    *,
    character_id: int,
) -> tuple[str | None, list[CharacterAlias]]:
    async with database._require_pool().acquire() as connection:
        name = await connection.fetchval(
            "SELECT name FROM characters WHERE id = $1",
            character_id,
        )
    if name is None:
        return None, []
    return str(name), await list_character_aliases(
        database,
        character_id=character_id,
    )

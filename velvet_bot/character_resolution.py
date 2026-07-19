from __future__ import annotations

from velvet_bot.character_aliases import normalize_character_alias
from velvet_bot.database import Character, Database


async def resolve_character(
    database: Database,
    value: str,
) -> Character | None:
    """Resolve a character by exact display name first, then by manual/name alias."""
    character = await database.get_character(value)
    if character is not None:
        return character

    normalized = normalize_character_alias(value)
    if not normalized:
        return None

    async with database.acquire() as connection:
        character_name = await connection.fetchval(
            """
            SELECT c.name
            FROM character_aliases AS a
            JOIN characters AS c ON c.id = a.character_id
            WHERE a.normalized_alias = $1
            ORDER BY CASE a.source WHEN 'name' THEN 0 ELSE 1 END, a.id
            LIMIT 1
            """,
            normalized,
        )
    if character_name is None:
        return None
    return await database.get_character(str(character_name))


__all__ = ("resolve_character",)

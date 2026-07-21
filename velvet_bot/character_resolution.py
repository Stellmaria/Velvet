from __future__ import annotations

from velvet_bot.character_aliases import normalize_character_alias
from velvet_bot.database import Character, Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID


async def load_character_by_id(
    database: Database,
    *,
    character_id: int,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> Character | None:
    """Load one character only when it belongs to the requested workspace."""
    async with database.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                id,
                workspace_id,
                name,
                created_by,
                created_in_chat,
                created_at,
                archive_chat_id,
                archive_thread_id,
                archive_topic_url
            FROM characters
            WHERE workspace_id = $1::BIGINT
              AND id = $2::BIGINT
            """,
            int(workspace_id),
            int(character_id),
        )
    if row is None:
        return None
    return Character(
        id=int(row["id"]),
        name=str(row["name"]),
        created_by=row["created_by"],
        created_in_chat=row["created_in_chat"],
        created_at=row["created_at"],
        archive_chat_id=row["archive_chat_id"],
        archive_thread_id=row["archive_thread_id"],
        archive_topic_url=row["archive_topic_url"],
        workspace_id=int(row["workspace_id"]),
    )


async def resolve_character(
    database: Database,
    value: str,
    *,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> Character | None:
    """Resolve a character by name or alias inside exactly one workspace."""
    target_workspace_id = int(workspace_id)
    if target_workspace_id == DEFAULT_WORKSPACE_ID:
        character = await database.get_character(value)
    else:
        character = await database.get_character(
            value,
            workspace_id=target_workspace_id,
        )
    if character is not None:
        return character

    normalized = normalize_character_alias(value)
    if not normalized:
        return None

    async with database.acquire() as connection:
        if target_workspace_id == DEFAULT_WORKSPACE_ID:
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
        else:
            character_name = await connection.fetchval(
                """
                SELECT c.name
                FROM workspace_character_aliases AS alias
                JOIN characters AS c
                  ON c.workspace_id = alias.workspace_id
                 AND c.id = alias.character_id
                WHERE alias.workspace_id = $2::BIGINT
                  AND alias.normalized_alias = $1::VARCHAR
                ORDER BY CASE alias.source WHEN 'name' THEN 0 ELSE 1 END, alias.id
                LIMIT 1
                """,
                normalized,
                target_workspace_id,
            )
    if character_name is None:
        return None
    if target_workspace_id == DEFAULT_WORKSPACE_ID:
        return await database.get_character(str(character_name))
    return await database.get_character(
        str(character_name),
        workspace_id=target_workspace_id,
    )


__all__ = ("load_character_by_id", "resolve_character")

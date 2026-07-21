from __future__ import annotations

from velvet_bot.database import Character, Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.topics import TopicReference


async def resolve_archive_workspace_id(
    database: Database,
    *,
    archive_chat_id: int,
) -> int:
    """Resolve an archive chat to one workspace, falling back to legacy Velvet."""
    acquire = getattr(database, "acquire", None)
    if not callable(acquire):
        return DEFAULT_WORKSPACE_ID
    async with acquire() as connection:
        fetchval = getattr(connection, "fetchval", None)
        if not callable(fetchval):
            return DEFAULT_WORKSPACE_ID
        value = await fetchval(
            """
            SELECT workspace_id
            FROM workspace_channels
            WHERE kind = 'archive'
              AND chat_id = $1::BIGINT
            LIMIT 1
            """,
            int(archive_chat_id),
        )
    return int(value) if value is not None else DEFAULT_WORKSPACE_ID


async def bind_character_archive_topic(
    database: Database,
    *,
    character_id: int,
    topic: TopicReference,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
) -> Character:
    """Add a topic link without removing links from other characters."""
    async with database.acquire() as connection:
        async with connection.transaction():
            row = await connection.fetchrow(
                """
                SELECT id
                FROM characters
                WHERE workspace_id = $1::BIGINT
                  AND id = $2::BIGINT
                FOR UPDATE
                """,
                int(workspace_id),
                int(character_id),
            )
            if row is None:
                raise ValueError("Персонаж больше не найден в этом пространстве.")

            await connection.execute(
                """
                INSERT INTO character_archive_topics (
                    character_id,
                    archive_chat_id,
                    archive_thread_id,
                    archive_topic_url
                )
                VALUES ($1::BIGINT, $2::BIGINT, $3::BIGINT, $4::TEXT)
                ON CONFLICT (character_id, archive_chat_id, archive_thread_id)
                DO UPDATE SET archive_topic_url = EXCLUDED.archive_topic_url
                """,
                int(character_id),
                int(topic.chat_id),
                int(topic.thread_id),
                topic.url,
            )
            updated = await connection.fetchrow(
                """
                UPDATE characters
                SET archive_chat_id = $3::BIGINT,
                    archive_thread_id = $4::BIGINT,
                    archive_topic_url = $5::TEXT
                WHERE workspace_id = $1::BIGINT
                  AND id = $2::BIGINT
                RETURNING
                    id,
                    workspace_id,
                    name,
                    created_by,
                    created_in_chat,
                    created_at,
                    archive_chat_id,
                    archive_thread_id,
                    archive_topic_url
                """,
                int(workspace_id),
                int(character_id),
                int(topic.chat_id),
                int(topic.thread_id),
                topic.url,
            )
    if updated is None:
        raise ValueError("Персонаж больше не найден в этом пространстве.")
    return _row_to_character(updated)


async def list_characters_by_archive_topic(
    database: Database,
    *,
    archive_chat_id: int,
    archive_thread_id: int,
    workspace_id: int | None = None,
) -> list[Character]:
    target_workspace_id = (
        int(workspace_id)
        if workspace_id is not None
        else await resolve_archive_workspace_id(
            database,
            archive_chat_id=archive_chat_id,
        )
    )
    acquire = getattr(database, "acquire", None)
    if not callable(acquire):
        legacy_lookup = getattr(database, "get_character_by_archive_topic", None)
        if not callable(legacy_lookup):
            return []
        try:
            character = await legacy_lookup(
                archive_chat_id,
                archive_thread_id,
                workspace_id=target_workspace_id,
            )
        except TypeError:
            character = await legacy_lookup(archive_chat_id, archive_thread_id)
        if character is not None and not hasattr(character, "workspace_id"):
            try:
                setattr(character, "workspace_id", target_workspace_id)
            except (AttributeError, TypeError):
                pass
        return [character] if character is not None else []

    async with acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT DISTINCT
                character.id,
                character.workspace_id,
                character.name,
                character.normalized_name,
                character.created_by,
                character.created_in_chat,
                character.created_at,
                character.archive_chat_id,
                character.archive_thread_id,
                character.archive_topic_url
            FROM characters AS character
            LEFT JOIN character_archive_topics AS topic
              ON topic.character_id = character.id
            WHERE character.workspace_id = $3::BIGINT
              AND (
                    (
                        topic.archive_chat_id = $1::BIGINT
                        AND topic.archive_thread_id = $2::BIGINT
                    )
                    OR (
                        character.archive_chat_id = $1::BIGINT
                        AND character.archive_thread_id = $2::BIGINT
                    )
              )
            ORDER BY character.normalized_name, character.id
            """,
            int(archive_chat_id),
            int(archive_thread_id),
            target_workspace_id,
        )
    return [_row_to_character(row) for row in rows]


async def list_archive_topic_characters(
    database: Database,
    *,
    archive_chat_id: int,
    archive_thread_id: int,
    workspace_id: int | None = None,
) -> list[Character]:
    return await list_characters_by_archive_topic(
        database,
        archive_chat_id=archive_chat_id,
        archive_thread_id=archive_thread_id,
        workspace_id=workspace_id,
    )


def _row_to_character(row) -> Character:
    return Character(
        id=int(row["id"]),
        name=str(row["name"]),
        created_by=row["created_by"],
        created_in_chat=row["created_in_chat"],
        created_at=row["created_at"],
        archive_chat_id=row["archive_chat_id"],
        archive_thread_id=row["archive_thread_id"],
        archive_topic_url=row["archive_topic_url"],
        workspace_id=(
            int(row["workspace_id"])
            if "workspace_id" in row
            else DEFAULT_WORKSPACE_ID
        ),
    )


__all__ = (
    "bind_character_archive_topic",
    "list_archive_topic_characters",
    "list_characters_by_archive_topic",
    "resolve_archive_workspace_id",
)

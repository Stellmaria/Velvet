from __future__ import annotations

from velvet_bot.database import Character, Database
from velvet_bot.topics import TopicReference


async def bind_character_archive_topic(
    database: Database,
    *,
    character_id: int,
    topic: TopicReference,
) -> Character:
    """Add a topic link without removing links from other characters."""
    async with database.acquire() as connection:
        async with connection.transaction():
            row = await connection.fetchrow(
                """
                SELECT id
                FROM characters
                WHERE id = $1::BIGINT
                FOR UPDATE
                """,
                int(character_id),
            )
            if row is None:
                raise ValueError("Персонаж больше не найден.")

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
                SET archive_chat_id = $2::BIGINT,
                    archive_thread_id = $3::BIGINT,
                    archive_topic_url = $4::TEXT
                WHERE id = $1::BIGINT
                RETURNING
                    id,
                    name,
                    created_by,
                    created_in_chat,
                    created_at,
                    archive_chat_id,
                    archive_thread_id,
                    archive_topic_url
                """,
                int(character_id),
                int(topic.chat_id),
                int(topic.thread_id),
                topic.url,
            )
    if updated is None:
        raise ValueError("Персонаж больше не найден.")
    return _row_to_character(updated)


async def list_characters_by_archive_topic(
    database: Database,
    *,
    archive_chat_id: int,
    archive_thread_id: int,
) -> list[Character]:
    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT DISTINCT
                c.id,
                c.name,
                c.created_by,
                c.created_in_chat,
                c.created_at,
                c.archive_chat_id,
                c.archive_thread_id,
                c.archive_topic_url
            FROM characters AS c
            LEFT JOIN character_archive_topics AS topic
              ON topic.character_id = c.id
            WHERE (
                    topic.archive_chat_id = $1::BIGINT
                AND topic.archive_thread_id = $2::BIGINT
            ) OR (
                    c.archive_chat_id = $1::BIGINT
                AND c.archive_thread_id = $2::BIGINT
            )
            ORDER BY c.normalized_name, c.id
            """,
            int(archive_chat_id),
            int(archive_thread_id),
        )
    return [_row_to_character(row) for row in rows]


async def list_archive_topic_characters(
    database: Database,
    *,
    archive_chat_id: int,
    archive_thread_id: int,
) -> list[Character]:
    return await list_characters_by_archive_topic(
        database,
        archive_chat_id=archive_chat_id,
        archive_thread_id=archive_thread_id,
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
    )


__all__ = (
    "bind_character_archive_topic",
    "list_archive_topic_characters",
    "list_characters_by_archive_topic",
)

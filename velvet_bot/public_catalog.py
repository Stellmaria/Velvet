from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.database import Character, Database


@dataclass(frozen=True, slots=True)
class PublicCharacterItem:
    character: Character
    media_count: int


@dataclass(frozen=True, slots=True)
class PublicCharacterPage:
    items: list[PublicCharacterItem]
    page: int
    page_size: int
    total_characters: int

    @property
    def total_pages(self) -> int:
        if self.total_characters <= 0:
            return 1
        return (self.total_characters + self.page_size - 1) // self.page_size


@dataclass(frozen=True, slots=True)
class PublicMediaState:
    like_count: int
    liked_by_user: bool
    subscribed: bool


async def list_public_characters(
    database: Database,
    *,
    page: int = 0,
    page_size: int = 8,
) -> PublicCharacterPage:
    safe_page_size = max(1, min(page_size, 12))
    safe_page = max(0, page)

    async with database._require_pool().acquire() as connection:
        total = int(
            await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT c.id
                    FROM characters AS c
                    JOIN character_media AS cm ON cm.character_id = c.id
                    GROUP BY c.id
                ) AS public_characters
                """
            )
            or 0
        )

        total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
        normalized_page = min(safe_page, total_pages - 1)
        rows = await connection.fetch(
            """
            SELECT
                c.id,
                c.name,
                c.created_by,
                c.created_in_chat,
                c.created_at,
                c.archive_chat_id,
                c.archive_thread_id,
                c.archive_topic_url,
                COUNT(cm.media_id) AS media_count
            FROM characters AS c
            JOIN character_media AS cm ON cm.character_id = c.id
            GROUP BY c.id
            ORDER BY c.normalized_name, c.id
            OFFSET $1
            LIMIT $2
            """,
            normalized_page * safe_page_size,
            safe_page_size,
        )

    items = [
        PublicCharacterItem(
            character=Character(
                id=int(row["id"]),
                name=str(row["name"]),
                created_by=row["created_by"],
                created_in_chat=row["created_in_chat"],
                created_at=row["created_at"],
                archive_chat_id=row["archive_chat_id"],
                archive_thread_id=row["archive_thread_id"],
                archive_topic_url=row["archive_topic_url"],
            ),
            media_count=int(row["media_count"] or 0),
        )
        for row in rows
    ]
    return PublicCharacterPage(
        items=items,
        page=normalized_page,
        page_size=safe_page_size,
        total_characters=total,
    )


async def get_public_media_state(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    user_id: int,
) -> PublicMediaState:
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                (
                    SELECT COUNT(*)
                    FROM character_media_likes
                    WHERE character_id = $1 AND media_id = $2
                ) AS like_count,
                EXISTS (
                    SELECT 1
                    FROM character_media_likes
                    WHERE character_id = $1 AND media_id = $2 AND user_id = $3
                ) AS liked_by_user,
                EXISTS (
                    SELECT 1
                    FROM character_subscriptions
                    WHERE character_id = $1 AND user_id = $3
                ) AS subscribed
            """,
            character_id,
            media_id,
            user_id,
        )

    return PublicMediaState(
        like_count=int(row["like_count"] or 0),
        liked_by_user=bool(row["liked_by_user"]),
        subscribed=bool(row["subscribed"]),
    )


async def toggle_public_like(
    database: Database,
    *,
    character_id: int,
    media_id: int,
    user_id: int,
) -> tuple[bool, int]:
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            deleted = await connection.fetchval(
                """
                DELETE FROM character_media_likes
                WHERE character_id = $1 AND media_id = $2 AND user_id = $3
                RETURNING 1
                """,
                character_id,
                media_id,
                user_id,
            )
            liked = deleted is None
            if liked:
                inserted = await connection.fetchval(
                    """
                    INSERT INTO character_media_likes (character_id, media_id, user_id)
                    VALUES ($1, $2, $3)
                    ON CONFLICT DO NOTHING
                    RETURNING 1
                    """,
                    character_id,
                    media_id,
                    user_id,
                )
                liked = inserted is not None

            like_count = int(
                await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM character_media_likes
                    WHERE character_id = $1 AND media_id = $2
                    """,
                    character_id,
                    media_id,
                )
                or 0
            )

    return liked, like_count


async def toggle_character_subscription(
    database: Database,
    *,
    character_id: int,
    user_id: int,
) -> bool:
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            deleted = await connection.fetchval(
                """
                DELETE FROM character_subscriptions
                WHERE character_id = $1 AND user_id = $2
                RETURNING 1
                """,
                character_id,
                user_id,
            )
            if deleted is not None:
                return False

            inserted = await connection.fetchval(
                """
                INSERT INTO character_subscriptions (character_id, user_id)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
                RETURNING 1
                """,
                character_id,
                user_id,
            )
            return inserted is not None


async def list_character_subscriber_ids(
    database: Database,
    character_id: int,
    *,
    exclude_user_id: int | None = None,
) -> list[int]:
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT user_id
            FROM character_subscriptions
            WHERE character_id = $1
              AND ($2::BIGINT IS NULL OR user_id <> $2)
            ORDER BY created_at, user_id
            """,
            character_id,
            exclude_user_id,
        )
    return [int(row["user_id"]) for row in rows]


async def remove_character_subscription(
    database: Database,
    *,
    character_id: int,
    user_id: int,
) -> None:
    async with database._require_pool().acquire() as connection:
        await connection.execute(
            """
            DELETE FROM character_subscriptions
            WHERE character_id = $1 AND user_id = $2
            """,
            character_id,
            user_id,
        )

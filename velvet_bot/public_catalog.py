from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.character_directory import (
    CategorySummary,
    CharacterDirectoryItem,
    CharacterDirectoryPage,
    list_category_summaries,
    list_character_directory,
)
from velvet_bot.database import Database

PublicCharacterItem = CharacterDirectoryItem
PublicCharacterPage = CharacterDirectoryPage


@dataclass(frozen=True, slots=True)
class PublicMediaState:
    like_count: int
    liked_by_user: bool
    subscribed: bool


async def list_public_categories(database: Database) -> list[CategorySummary]:
    return await list_category_summaries(database, public_only=True)


async def list_public_characters(
    database: Database,
    *,
    category: str,
    page: int = 0,
    page_size: int = 6,
) -> PublicCharacterPage:
    return await list_character_directory(
        database,
        category=category,
        page=page,
        page_size=page_size,
        public_only=True,
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

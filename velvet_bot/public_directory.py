from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.characters.constants import (
    CATEGORY_EMOJI,
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    STORY_REQUIRED_SQL,
    UNIVERSE_EMOJI,
    UNIVERSE_LABELS,
    UNIVERSE_ORDER,
)
from velvet_bot.domains.characters.models import (
    CategorySummary,
    CharacterDirectoryItem,
    CharacterDirectoryPage,
    CharacterRecord,
    UniverseSummary,
)
from velvet_bot.domains.stories.models import StorySummary


async def list_visible_categories(database: Database) -> list[CategorySummary]:
    async with database.acquire() as connection:
        rows = await connection.fetch(
            f"""
            SELECT c.category, COUNT(DISTINCT c.id) AS character_count
            FROM characters AS c
            JOIN character_media AS cm
              ON cm.character_id = c.id
             AND cm.is_public = TRUE
            WHERE c.category IS NOT NULL
              AND c.universe IS NOT NULL
              AND (
                    c.universe NOT IN {STORY_REQUIRED_SQL}
                    OR EXISTS (
                        SELECT 1
                        FROM character_story_links AS ready_link
                        WHERE ready_link.character_id = c.id
                    )
                  )
            GROUP BY c.category
            """
        )
    counts = {
        str(row["category"]): int(row["character_count"] or 0)
        for row in rows
    }
    return [
        CategorySummary(
            key=key,
            label=CATEGORY_LABELS[key],
            emoji=CATEGORY_EMOJI[key],
            character_count=counts.get(key, 0),
        )
        for key in CATEGORY_ORDER
    ]


async def list_visible_universes(
    database: Database,
    *,
    category: str,
) -> list[UniverseSummary]:
    async with database.acquire() as connection:
        rows = await connection.fetch(
            f"""
            SELECT c.universe, COUNT(DISTINCT c.id) AS character_count
            FROM characters AS c
            JOIN character_media AS cm
              ON cm.character_id = c.id
             AND cm.is_public = TRUE
            WHERE c.category = $1::VARCHAR
              AND c.universe IS NOT NULL
              AND (
                    c.universe NOT IN {STORY_REQUIRED_SQL}
                    OR EXISTS (
                        SELECT 1
                        FROM character_story_links AS ready_link
                        WHERE ready_link.character_id = c.id
                    )
                  )
            GROUP BY c.universe
            """,
            category,
        )
    counts = {
        str(row["universe"]): int(row["character_count"] or 0)
        for row in rows
    }
    return [
        UniverseSummary(
            key=key,
            label=UNIVERSE_LABELS[key],
            emoji=UNIVERSE_EMOJI[key],
            character_count=counts.get(key, 0),
        )
        for key in UNIVERSE_ORDER
    ]


async def list_visible_stories(
    database: Database,
    *,
    category: str,
    universe: str,
) -> list[StorySummary]:
    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                story.id,
                story.universe,
                story.key,
                story.short_label,
                story.title,
                story.release_order,
                story.released_on,
                story.release_precision,
                COUNT(DISTINCT character.id) AS character_count
            FROM character_stories AS story
            JOIN character_story_links AS link ON link.story_id = story.id
            JOIN characters AS character ON character.id = link.character_id
            JOIN character_media AS media
              ON media.character_id = character.id
             AND media.is_public = TRUE
            WHERE story.universe = $1::VARCHAR
              AND character.category = $2::VARCHAR
              AND character.universe = $1::VARCHAR
            GROUP BY story.id
            ORDER BY
                story.release_order DESC,
                story.released_on DESC NULLS LAST,
                story.title,
                story.id
            """,
            universe,
            category,
        )
    return [
        StorySummary(
            id=int(row["id"]),
            universe=str(row["universe"]),
            key=str(row["key"]),
            short_label=str(row["short_label"]),
            title=str(row["title"]),
            character_count=int(row["character_count"] or 0),
            release_order=int(row["release_order"] or 0),
            released_on=row["released_on"],
            release_precision=str(row["release_precision"] or "unknown"),
        )
        for row in rows
    ]


async def list_visible_characters(
    database: Database,
    *,
    category: str,
    universe: str | None = None,
    story_id: int | None = None,
    page: int = 0,
    page_size: int = 6,
) -> CharacterDirectoryPage:
    safe_page_size = max(1, min(int(page_size), 10))
    safe_page = max(0, int(page))
    async with database.acquire() as connection:
        total = int(
            await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT character.id
                    FROM characters AS character
                    JOIN character_media AS media
                      ON media.character_id = character.id
                     AND media.is_public = TRUE
                    WHERE character.category = $1::VARCHAR
                      AND ($2::VARCHAR IS NULL OR character.universe = $2::VARCHAR)
                      AND (
                            $3::BIGINT IS NULL
                            OR EXISTS (
                                SELECT 1
                                FROM character_story_links AS selected_link
                                WHERE selected_link.character_id = character.id
                                  AND selected_link.story_id = $3::BIGINT
                            )
                          )
                    GROUP BY character.id
                ) AS visible_characters
                """,
                category,
                universe,
                story_id,
            )
            or 0
        )
        total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
        normalized_page = min(safe_page, total_pages - 1)
        rows = await connection.fetch(
            """
            SELECT
                character.id,
                character.name,
                character.created_by,
                character.created_in_chat,
                character.created_at,
                character.archive_chat_id,
                character.archive_thread_id,
                character.archive_topic_url,
                character.category,
                character.universe,
                character.prompt_post_url,
                character.story_id,
                story.short_label AS story_short_label,
                story.title AS story_title,
                COUNT(media.media_id) AS media_count
            FROM characters AS character
            LEFT JOIN character_stories AS story ON story.id = character.story_id
            JOIN character_media AS media
              ON media.character_id = character.id
             AND media.is_public = TRUE
            WHERE character.category = $1::VARCHAR
              AND ($2::VARCHAR IS NULL OR character.universe = $2::VARCHAR)
              AND (
                    $3::BIGINT IS NULL
                    OR EXISTS (
                        SELECT 1
                        FROM character_story_links AS selected_link
                        WHERE selected_link.character_id = character.id
                          AND selected_link.story_id = $3::BIGINT
                    )
                  )
            GROUP BY character.id, story.id
            ORDER BY character.normalized_name, character.id
            OFFSET $4::INTEGER
            LIMIT $5::INTEGER
            """,
            category,
            universe,
            story_id,
            normalized_page * safe_page_size,
            safe_page_size,
        )
        selected_story = None
        if story_id is not None and universe is not None:
            selected_story = await connection.fetchrow(
                """
                SELECT id, short_label, title
                FROM character_stories
                WHERE id = $1::BIGINT AND universe = $2::VARCHAR
                """,
                int(story_id),
                universe,
            )

    return CharacterDirectoryPage(
        items=[_row_to_item(row) for row in rows],
        category=category,
        page=normalized_page,
        page_size=safe_page_size,
        total_characters=total,
        universe=universe,
        story_id=story_id,
        story_short_label=(
            str(selected_story["short_label"])
            if selected_story is not None
            else None
        ),
        story_title=(
            str(selected_story["title"])
            if selected_story is not None
            else None
        ),
    )


def _row_to_item(row) -> CharacterDirectoryItem:
    return CharacterDirectoryItem(
        character=CharacterRecord(
            id=int(row["id"]),
            name=str(row["name"]),
            created_by=row["created_by"],
            created_in_chat=row["created_in_chat"],
            created_at=row["created_at"],
            archive_chat_id=row["archive_chat_id"],
            archive_thread_id=row["archive_thread_id"],
            archive_topic_url=row["archive_topic_url"],
        ),
        category=row["category"],
        prompt_post_url=row["prompt_post_url"],
        media_count=int(row["media_count"] or 0),
        universe=row["universe"],
        story_id=(int(row["story_id"]) if row["story_id"] is not None else None),
        story_short_label=row["story_short_label"],
        story_title=row["story_title"],
    )


__all__ = (
    "list_visible_categories",
    "list_visible_characters",
    "list_visible_stories",
    "list_visible_universes",
)

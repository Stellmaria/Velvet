from __future__ import annotations

from velvet_bot.character_directory import (
    CATEGORY_ORDER,
    UNIVERSE_ORDER,
    CharacterDirectoryItem,
    CharacterDirectoryPage,
)
from velvet_bot.database import Character, Database
from velvet_bot.public_directory_catalog import UNASSIGNED_STORY_ID


def _row_to_item(row) -> CharacterDirectoryItem:
    character = Character(
        id=int(row["id"]),
        name=str(row["name"]),
        created_by=row["created_by"],
        created_in_chat=row["created_in_chat"],
        created_at=row["created_at"],
        archive_chat_id=row["archive_chat_id"],
        archive_thread_id=row["archive_thread_id"],
        archive_topic_url=row["archive_topic_url"],
    )
    return CharacterDirectoryItem(
        character=character,
        category=row["category"],
        prompt_post_url=row["prompt_post_url"],
        media_count=int(row["media_count"] or 0),
        universe=row["universe"],
        story_id=(int(row["story_id"]) if row["story_id"] is not None else None),
        story_short_label=row["story_short_label"],
        story_title=row["story_title"],
    )


async def list_viewer_characters(
    database: Database,
    *,
    category: str,
    universe: str,
    story_id: int | None,
    page: int = 0,
    page_size: int = 6,
    include_incomplete: bool,
) -> CharacterDirectoryPage:
    if category not in CATEGORY_ORDER:
        raise ValueError("Неизвестная категория архива.")
    if universe not in UNIVERSE_ORDER:
        raise ValueError("Неизвестная вселенная архива.")
    if story_id == UNASSIGNED_STORY_ID and not include_incomplete:
        raise ValueError("Раздел без истории доступен только редактору архива.")

    safe_page_size = max(1, min(page_size, 10))
    safe_page = max(0, page)
    story_condition = """
        (
            ($3::BIGINT IS NULL)
            OR ($3 = -1 AND c.story_id IS NULL)
            OR ($3 > 0 AND c.story_id = $3)
        )
    """

    async with database._require_pool().acquire() as connection:
        total = int(
            await connection.fetchval(
                f"""
                SELECT COUNT(*)
                FROM (
                    SELECT c.id
                    FROM characters AS c
                    JOIN character_media AS cm ON cm.character_id = c.id
                    WHERE c.category = $1
                      AND c.universe = $2
                      AND {story_condition}
                    GROUP BY c.id
                ) AS directory
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
            f"""
            SELECT
                c.id, c.name, c.created_by, c.created_in_chat, c.created_at,
                c.archive_chat_id, c.archive_thread_id, c.archive_topic_url,
                c.category, c.universe, c.prompt_post_url, c.story_id,
                s.short_label AS story_short_label,
                s.title AS story_title,
                COUNT(cm.media_id) AS media_count
            FROM characters AS c
            LEFT JOIN character_stories AS s ON s.id = c.story_id
            JOIN character_media AS cm ON cm.character_id = c.id
            WHERE c.category = $1
              AND c.universe = $2
              AND {story_condition}
            GROUP BY c.id, s.id
            ORDER BY c.normalized_name, c.id
            OFFSET $4
            LIMIT $5
            """,
            category,
            universe,
            story_id,
            normalized_page * safe_page_size,
            safe_page_size,
        )

        selected_story = None
        if story_id is not None and story_id > 0:
            selected_story = await connection.fetchrow(
                """
                SELECT short_label, title
                FROM character_stories
                WHERE id = $1 AND universe = $2
                """,
                story_id,
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
            "—"
            if story_id == UNASSIGNED_STORY_ID
            else str(selected_story["short_label"])
            if selected_story is not None
            else None
        ),
        story_title=(
            "Без истории"
            if story_id == UNASSIGNED_STORY_ID
            else str(selected_story["title"])
            if selected_story is not None
            else None
        ),
    )

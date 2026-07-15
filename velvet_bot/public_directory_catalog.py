from __future__ import annotations

from velvet_bot.character_directory import (
    CATEGORY_EMOJI,
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    UNIVERSE_EMOJI,
    UNIVERSE_LABELS,
    UNIVERSE_ORDER,
    CategorySummary,
    CharacterDirectoryItem,
    CharacterDirectoryPage,
    UniverseSummary,
)
from velvet_bot.database import Character, Database
from velvet_bot.story_catalog import StorySummary

STORY_REQUIRED_UNIVERSES = ("shs", "kr", "lm", "idm", "lagerta")
UNASSIGNED_STORY_ID = -1


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


def _row_to_item(row) -> CharacterDirectoryItem:
    return CharacterDirectoryItem(
        character=_row_to_character(row),
        category=row["category"],
        prompt_post_url=row["prompt_post_url"],
        media_count=int(row["media_count"] or 0),
        universe=row["universe"],
        story_id=(int(row["story_id"]) if row["story_id"] is not None else None),
        story_short_label=row["story_short_label"],
        story_title=row["story_title"],
    )


async def list_viewer_categories(
    database: Database,
    *,
    include_incomplete: bool,
) -> list[CategorySummary]:
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT c.category, COUNT(DISTINCT c.id) AS character_count
            FROM characters AS c
            JOIN character_media AS cm ON cm.character_id = c.id
            WHERE c.category IS NOT NULL
              AND c.universe IS NOT NULL
              AND (
                    $1::BOOLEAN = TRUE
                    OR c.universe <> ALL($2::TEXT[])
                    OR c.story_id IS NOT NULL
                  )
            GROUP BY c.category
            """,
            include_incomplete,
            list(STORY_REQUIRED_UNIVERSES),
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


async def list_viewer_universes(
    database: Database,
    *,
    category: str,
    include_incomplete: bool,
) -> list[UniverseSummary]:
    if category not in CATEGORY_ORDER:
        raise ValueError("Неизвестная категория архива.")
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT c.universe, COUNT(DISTINCT c.id) AS character_count
            FROM characters AS c
            JOIN character_media AS cm ON cm.character_id = c.id
            WHERE c.category = $1
              AND c.universe IS NOT NULL
              AND (
                    $2::BOOLEAN = TRUE
                    OR c.universe <> ALL($3::TEXT[])
                    OR c.story_id IS NOT NULL
                  )
            GROUP BY c.universe
            """,
            category,
            include_incomplete,
            list(STORY_REQUIRED_UNIVERSES),
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


async def list_viewer_stories(
    database: Database,
    *,
    category: str,
    universe: str,
    include_unassigned: bool,
) -> list[StorySummary]:
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                s.id,
                s.universe,
                s.key,
                s.short_label,
                s.title,
                s.release_order,
                s.released_on,
                s.release_precision,
                COUNT(DISTINCT c.id) AS character_count
            FROM character_stories AS s
            JOIN characters AS c ON c.story_id = s.id
            JOIN character_media AS cm ON cm.character_id = c.id
            WHERE s.universe = $1
              AND c.category = $2
              AND c.universe = $1
            GROUP BY s.id
            ORDER BY
                s.release_order DESC,
                s.released_on DESC NULLS LAST,
                s.title,
                s.id
            """,
            universe,
            category,
        )
        unassigned_count = 0
        if include_unassigned:
            unassigned_count = int(
                await connection.fetchval(
                    """
                    SELECT COUNT(DISTINCT c.id)
                    FROM characters AS c
                    JOIN character_media AS cm ON cm.character_id = c.id
                    WHERE c.category = $1
                      AND c.universe = $2
                      AND c.story_id IS NULL
                    """,
                    category,
                    universe,
                )
                or 0
            )

    summaries = [
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
    if unassigned_count:
        summaries.insert(
            0,
            StorySummary(
                id=UNASSIGNED_STORY_ID,
                universe=universe,
                key="unassigned",
                short_label="—",
                title="Без истории",
                character_count=unassigned_count,
                release_order=2_147_483_647,
                released_on=None,
                release_precision="unknown",
            ),
        )
    return summaries


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
    if story_id == UNASSIGNED_STORY_ID:
        story_condition = "c.story_id IS NULL"
    elif story_id is None:
        story_condition = "TRUE"
    else:
        story_condition = "c.story_id = $3"

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

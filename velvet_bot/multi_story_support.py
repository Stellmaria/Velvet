from __future__ import annotations

from dataclasses import dataclass

import velvet_bot.character_directory as directory
import velvet_bot.story_catalog as stories
from velvet_bot.database import Database

_STORY_REQUIRED_SQL = "('shs', 'kr', 'lm', 'idm', 'lagerta')"


@dataclass(frozen=True, slots=True)
class AssignedCharacterStory:
    story: stories.CharacterStory
    is_primary: bool


async def list_assigned_character_stories(
    database: Database,
    *,
    character_id: int,
) -> list[AssignedCharacterStory]:
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            f"""
            SELECT
                {stories._STORY_COLUMNS},
                link.is_primary
            FROM character_story_links AS link
            JOIN character_stories AS story ON story.id = link.story_id
            WHERE link.character_id = $1
            ORDER BY
                link.is_primary DESC,
                story.release_order DESC,
                story.released_on DESC NULLS LAST,
                story.title,
                story.id
            """.replace("id,", "story.id,", 1)
            .replace("universe,", "story.universe,", 1)
            .replace("key,", "story.key,", 1)
            .replace("short_label,", "story.short_label,", 1)
            .replace("title,", "story.title,", 1)
            .replace("sort_order,", "story.sort_order,", 1)
            .replace("release_order,", "story.release_order,", 1)
            .replace("released_on,", "story.released_on,", 1)
            .replace("release_precision", "story.release_precision", 1),
            character_id,
        )
    return [
        AssignedCharacterStory(
            story=stories._row_to_story(row),
            is_primary=bool(row["is_primary"]),
        )
        for row in rows
    ]


async def _select_new_primary(connection, character_id: int) -> int | None:
    story_id = await connection.fetchval(
        """
        SELECT link.story_id
        FROM character_story_links AS link
        JOIN character_stories AS story ON story.id = link.story_id
        WHERE link.character_id = $1
        ORDER BY
            story.release_order DESC,
            story.released_on DESC NULLS LAST,
            story.title,
            story.id
        LIMIT 1
        """,
        character_id,
    )
    await connection.execute(
        "UPDATE character_story_links SET is_primary = FALSE WHERE character_id = $1",
        character_id,
    )
    if story_id is not None:
        await connection.execute(
            """
            UPDATE character_story_links
            SET is_primary = TRUE
            WHERE character_id = $1 AND story_id = $2
            """,
            character_id,
            int(story_id),
        )
    await connection.execute(
        "UPDATE characters SET story_id = $2 WHERE id = $1",
        character_id,
        int(story_id) if story_id is not None else None,
    )
    return int(story_id) if story_id is not None else None


async def toggle_character_story(
    database: Database,
    *,
    character_id: int,
    story_id: int,
    assigned_by: int | None = None,
) -> bool:
    """Toggle one KR story and keep characters.story_id as a primary fallback."""
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            character = await connection.fetchrow(
                "SELECT id, universe, story_id FROM characters WHERE id = $1 FOR UPDATE",
                character_id,
            )
            story = await connection.fetchrow(
                "SELECT id, universe FROM character_stories WHERE id = $1",
                story_id,
            )
            if character is None or story is None:
                raise ValueError("Персонаж или история больше не найдены.")
            if character["universe"] != "kr" or story["universe"] != "kr":
                raise ValueError("Множественный выбор историй доступен только для КР.")

            exists = await connection.fetchval(
                """
                SELECT TRUE
                FROM character_story_links
                WHERE character_id = $1 AND story_id = $2
                """,
                character_id,
                story_id,
            )
            if exists:
                await connection.execute(
                    """
                    DELETE FROM character_story_links
                    WHERE character_id = $1 AND story_id = $2
                    """,
                    character_id,
                    story_id,
                )
                if character["story_id"] == story_id:
                    await _select_new_primary(connection, character_id)
                return False

            has_primary = bool(
                await connection.fetchval(
                    """
                    SELECT TRUE
                    FROM character_story_links
                    WHERE character_id = $1 AND is_primary
                    LIMIT 1
                    """,
                    character_id,
                )
            )
            await connection.execute(
                """
                INSERT INTO character_story_links (
                    character_id, story_id, is_primary, assigned_by
                )
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (character_id, story_id) DO NOTHING
                """,
                character_id,
                story_id,
                not has_primary,
                assigned_by,
            )
            if not has_primary:
                await connection.execute(
                    "UPDATE characters SET story_id = $2 WHERE id = $1",
                    character_id,
                    story_id,
                )
            return True


async def clear_character_stories(
    database: Database,
    *,
    character_id: int,
) -> None:
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            result = await connection.execute(
                "DELETE FROM character_story_links WHERE character_id = $1",
                character_id,
            )
            updated = await connection.execute(
                "UPDATE characters SET story_id = NULL WHERE id = $1",
                character_id,
            )
    if updated == "UPDATE 0":
        raise ValueError("Персонаж не найден.")


async def set_character_story(
    database: Database,
    *,
    character_id: int,
    story_id: int | None,
) -> None:
    """Replace story selection for single-story flows and command compatibility."""
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            character = await connection.fetchrow(
                "SELECT id, universe FROM characters WHERE id = $1 FOR UPDATE",
                character_id,
            )
            if character is None:
                raise ValueError("Персонаж не найден.")
            if story_id is not None:
                story = await connection.fetchrow(
                    "SELECT id, universe FROM character_stories WHERE id = $1",
                    story_id,
                )
                if story is None or story["universe"] != character["universe"]:
                    raise ValueError(
                        "История относится к другой вселенной или больше не существует."
                    )
            await connection.execute(
                "DELETE FROM character_story_links WHERE character_id = $1",
                character_id,
            )
            if story_id is not None:
                await connection.execute(
                    """
                    INSERT INTO character_story_links (
                        character_id, story_id, is_primary
                    )
                    VALUES ($1, $2, TRUE)
                    """,
                    character_id,
                    story_id,
                )
            await connection.execute(
                "UPDATE characters SET story_id = $2 WHERE id = $1",
                character_id,
                story_id,
            )


async def set_character_universe(
    database: Database,
    *,
    character_id: int,
    universe: str | None,
) -> None:
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            current = await connection.fetchrow(
                "SELECT universe FROM characters WHERE id = $1 FOR UPDATE",
                character_id,
            )
            if current is None:
                raise ValueError("Персонаж не найден.")
            if current["universe"] != universe:
                await connection.execute(
                    "DELETE FROM character_story_links WHERE character_id = $1",
                    character_id,
                )
                await connection.execute(
                    """
                    UPDATE characters
                    SET universe = $2, story_id = NULL
                    WHERE id = $1
                    """,
                    character_id,
                    universe,
                )
            else:
                await connection.execute(
                    "UPDATE characters SET universe = $2 WHERE id = $1",
                    character_id,
                    universe,
                )


async def list_story_summaries(
    database: Database,
    *,
    category: str,
    universe: str,
    public_only: bool,
) -> list[stories.StorySummary]:
    async with database._require_pool().acquire() as connection:
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
                COUNT(DISTINCT character.id) FILTER (
                    WHERE character.category = $1
                      AND character.universe = $2
                      AND ($3::BOOLEAN = FALSE OR media.media_id IS NOT NULL)
                ) AS character_count
            FROM character_stories AS story
            LEFT JOIN character_story_links AS link ON link.story_id = story.id
            LEFT JOIN characters AS character ON character.id = link.character_id
            LEFT JOIN character_media AS media ON media.character_id = character.id
            WHERE story.universe = $2
            GROUP BY story.id
            ORDER BY
                story.release_order DESC,
                story.released_on DESC NULLS LAST,
                story.title,
                story.id
            """,
            category,
            universe,
            public_only,
        )
    result = [
        stories.StorySummary(
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
    return [item for item in result if item.character_count > 0] if public_only else result


async def list_category_summaries(
    database: Database,
    *,
    public_only: bool,
    include_uncategorized: bool = False,
) -> list[directory.CategorySummary]:
    keys = list(directory.CATEGORY_ORDER)
    if include_uncategorized:
        keys.append("uncategorized")
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            f"""
            SELECT
                COALESCE(character.category, 'uncategorized') AS category,
                COUNT(DISTINCT character.id) AS character_count
            FROM characters AS character
            LEFT JOIN character_media AS media ON media.character_id = character.id
            WHERE (
                $1::BOOLEAN = FALSE
                OR (
                    media.media_id IS NOT NULL
                    AND character.universe IS NOT NULL
                    AND (
                        character.universe NOT IN {_STORY_REQUIRED_SQL}
                        OR EXISTS (
                            SELECT 1
                            FROM character_story_links AS link
                            WHERE link.character_id = character.id
                        )
                    )
                )
            )
            GROUP BY COALESCE(character.category, 'uncategorized')
            """,
            public_only,
        )
    counts = {str(row["category"]): int(row["character_count"] or 0) for row in rows}
    return [
        directory.CategorySummary(
            key=key,
            label=directory.CATEGORY_LABELS[key],
            emoji=directory.CATEGORY_EMOJI[key],
            character_count=counts.get(key, 0),
        )
        for key in keys
    ]


async def list_universe_summaries(
    database: Database,
    *,
    category: str,
    public_only: bool,
    include_unassigned: bool = False,
) -> list[directory.UniverseSummary]:
    if category not in directory.CATEGORY_ORDER:
        raise ValueError("Неизвестная категория архива.")
    keys = list(directory.UNIVERSE_ORDER)
    if include_unassigned:
        keys.append("unassigned")
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            f"""
            SELECT
                COALESCE(character.universe, 'unassigned') AS universe,
                COUNT(DISTINCT character.id) AS character_count
            FROM characters AS character
            LEFT JOIN character_media AS media ON media.character_id = character.id
            WHERE character.category = $1
              AND (
                    $2::BOOLEAN = FALSE
                    OR (
                        media.media_id IS NOT NULL
                        AND (
                            character.universe NOT IN {_STORY_REQUIRED_SQL}
                            OR EXISTS (
                                SELECT 1
                                FROM character_story_links AS link
                                WHERE link.character_id = character.id
                            )
                        )
                    )
                  )
            GROUP BY COALESCE(character.universe, 'unassigned')
            """,
            category,
            public_only,
        )
    counts = {str(row["universe"]): int(row["character_count"] or 0) for row in rows}
    return [
        directory.UniverseSummary(
            key=key,
            label=directory.UNIVERSE_LABELS[key],
            emoji=directory.UNIVERSE_EMOJI[key],
            character_count=counts.get(key, 0),
        )
        for key in keys
    ]


async def list_character_directory(
    database: Database,
    *,
    category: str,
    page: int = 0,
    page_size: int = 6,
    public_only: bool,
    universe: str | None = None,
    story_id: int | None = None,
) -> directory.CharacterDirectoryPage:
    if category not in {*directory.CATEGORY_ORDER, "uncategorized"}:
        raise ValueError("Неизвестная категория архива.")
    if universe is not None and universe not in directory.UNIVERSE_ORDER:
        raise ValueError("Неизвестная вселенная архива.")
    if category == "uncategorized" and universe is not None:
        raise ValueError("Для раздела без категории фильтр вселенной недоступен.")
    if story_id is not None and universe is None:
        raise ValueError("Для фильтра по истории сначала нужна вселенная.")

    safe_page_size = max(1, min(page_size, 10))
    safe_page = max(0, page)
    category_condition = """
        (($1::TEXT = 'uncategorized' AND c.category IS NULL) OR c.category = $1)
    """
    universe_condition = "($3::TEXT IS NULL OR c.universe = $3)"
    story_condition = """
        ($4::BIGINT IS NULL OR EXISTS (
            SELECT 1
            FROM character_story_links AS selected_link
            WHERE selected_link.character_id = c.id
              AND selected_link.story_id = $4
        ))
    """
    public_condition = f"""
        (
            $2::BOOLEAN = FALSE
            OR (
                cm.media_id IS NOT NULL
                AND c.universe IS NOT NULL
                AND (
                    c.universe NOT IN {_STORY_REQUIRED_SQL}
                    OR EXISTS (
                        SELECT 1
                        FROM character_story_links AS ready_link
                        WHERE ready_link.character_id = c.id
                    )
                )
            )
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
                    LEFT JOIN character_media AS cm ON cm.character_id = c.id
                    WHERE {category_condition}
                      AND {public_condition}
                      AND {universe_condition}
                      AND {story_condition}
                    GROUP BY c.id
                ) AS filtered
                """,
                category,
                public_only,
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
                primary_story.short_label AS story_short_label,
                primary_story.title AS story_title,
                COUNT(DISTINCT cm.media_id) AS media_count
            FROM characters AS c
            LEFT JOIN character_stories AS primary_story ON primary_story.id = c.story_id
            LEFT JOIN character_media AS cm ON cm.character_id = c.id
            WHERE {category_condition}
              AND {public_condition}
              AND {universe_condition}
              AND {story_condition}
            GROUP BY c.id, primary_story.id
            ORDER BY c.normalized_name ASC, c.id ASC
            OFFSET $5
            LIMIT $6
            """,
            category,
            public_only,
            universe,
            story_id,
            normalized_page * safe_page_size,
            safe_page_size,
        )
        selected_story = None
        if story_id is not None:
            selected_story = await connection.fetchrow(
                """
                SELECT id, short_label, title
                FROM character_stories
                WHERE id = $1 AND universe = $2
                """,
                story_id,
                universe,
            )

    return directory.CharacterDirectoryPage(
        items=[directory._row_to_directory_item(row) for row in rows],
        category=category,
        page=normalized_page,
        page_size=safe_page_size,
        total_characters=total,
        universe=universe,
        story_id=story_id,
        story_short_label=(
            str(selected_story["short_label"]) if selected_story is not None else None
        ),
        story_title=(str(selected_story["title"]) if selected_story is not None else None),
    )


def install_multi_story_support() -> None:
    directory._STORY_REQUIRED_SQL = _STORY_REQUIRED_SQL
    directory.set_character_universe = set_character_universe
    directory.list_category_summaries = list_category_summaries
    directory.list_universe_summaries = list_universe_summaries
    directory.list_character_directory = list_character_directory
    stories.set_character_story = set_character_story
    stories.list_story_summaries = list_story_summaries

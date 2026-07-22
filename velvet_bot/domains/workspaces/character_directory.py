from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.characters.models import (
    CategorySummary,
    CharacterDirectoryItem,
    CharacterDirectoryPage,
    CharacterRecord,
    UniverseSummary,
)
from velvet_bot.domains.public_archive.visibility import public_media_visibility_sql
from velvet_bot.domains.stories.models import StorySummary


def _visibility_exists_sql(
    *,
    character_alias: str,
    include_restricted: bool,
) -> str:
    visibility = public_media_visibility_sql(
        link_alias="cm",
        file_alias="mf",
        include_adult_restricted=include_restricted,
        # Personal archives can show a protected Telegram document even when
        # cloud Bot API cannot build a photo preview. Download remains a
        # separate owner policy.
        include_oversized_images=True,
    )
    return f"""
        EXISTS (
            SELECT 1
            FROM character_media AS cm
            JOIN media_files AS mf ON mf.id = cm.media_id
            WHERE cm.character_id = {character_alias}.id
              AND ({visibility})
        )
    """.strip()


def _ready_sql(
    *,
    character_alias: str,
    public_only: bool,
    include_restricted: bool,
) -> str:
    if not public_only:
        return "TRUE"
    visible_media = _visibility_exists_sql(
        character_alias=character_alias,
        include_restricted=include_restricted,
    )
    return f"""
        {visible_media}
        AND {character_alias}.universe IS NOT NULL
        AND EXISTS (
            SELECT 1
            FROM workspace_universes AS ready_universe
            WHERE ready_universe.workspace_id = {character_alias}.workspace_id
              AND ready_universe.key = {character_alias}.universe
              AND ready_universe.is_enabled
              AND (
                    NOT ready_universe.requires_story
                    OR EXISTS (
                        SELECT 1
                        FROM workspace_character_story_links AS ready_link
                        JOIN workspace_stories AS ready_story
                          ON ready_story.workspace_id = ready_link.workspace_id
                         AND ready_story.id = ready_link.story_id
                         AND ready_story.is_enabled
                        WHERE ready_link.workspace_id = {character_alias}.workspace_id
                          AND ready_link.character_id = {character_alias}.id
                    )
                  )
        )
    """.strip()


def _media_count_sql(
    *,
    character_alias: str,
    public_only: bool,
    include_restricted: bool,
) -> str:
    condition = "TRUE"
    if public_only:
        condition = public_media_visibility_sql(
            link_alias="cm",
            file_alias="mf",
            include_adult_restricted=include_restricted,
            include_oversized_images=True,
        )
    return f"""
        (
            SELECT COUNT(*)
            FROM character_media AS cm
            JOIN media_files AS mf ON mf.id = cm.media_id
            WHERE cm.character_id = {character_alias}.id
              AND ({condition})
        )
    """.strip()


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
            workspace_id=int(row["workspace_id"]),
        ),
        category=row["category"],
        prompt_post_url=row["prompt_post_url"],
        media_count=int(row["media_count"] or 0),
        universe=row["universe"],
        story_id=(int(row["story_id"]) if row["story_id"] is not None else None),
        story_short_label=row["story_short_label"],
        story_title=row["story_title"],
    )


async def get_workspace_character_directory_item(
    database: Database,
    *,
    workspace_id: int,
    character_id: int,
    public_only: bool = False,
    include_restricted: bool = True,
) -> CharacterDirectoryItem | None:
    ready = _ready_sql(
        character_alias="character",
        public_only=public_only,
        include_restricted=include_restricted,
    )
    media_count = _media_count_sql(
        character_alias="character",
        public_only=public_only,
        include_restricted=include_restricted,
    )
    async with database.acquire() as connection:
        row = await connection.fetchrow(
            f"""
            SELECT
                character.id,
                character.workspace_id,
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
                primary_story.id AS story_id,
                primary_story.short_label AS story_short_label,
                primary_story.title AS story_title,
                {media_count} AS media_count
            FROM characters AS character
            LEFT JOIN LATERAL (
                SELECT story.id, story.short_label, story.title
                FROM workspace_character_story_links AS link
                JOIN workspace_stories AS story
                  ON story.workspace_id = link.workspace_id
                 AND story.id = link.story_id
                WHERE link.workspace_id = character.workspace_id
                  AND link.character_id = character.id
                  AND story.is_enabled
                ORDER BY
                    link.is_primary DESC,
                    story.sort_order,
                    story.title,
                    story.id
                LIMIT 1
            ) AS primary_story ON TRUE
            WHERE character.workspace_id = $1::BIGINT
              AND character.id = $2::BIGINT
              AND ({ready})
            """,
            int(workspace_id),
            int(character_id),
        )
    return _row_to_item(row) if row is not None else None


async def list_workspace_category_summaries(
    database: Database,
    *,
    workspace_id: int,
    public_only: bool,
    include_uncategorized: bool = False,
    include_restricted: bool = True,
) -> list[CategorySummary]:
    ready = _ready_sql(
        character_alias="character",
        public_only=public_only,
        include_restricted=include_restricted,
    )
    async with database.acquire() as connection:
        rows = await connection.fetch(
            f"""
            SELECT
                category.key,
                category.label,
                category.emoji,
                (
                    SELECT COUNT(*)
                    FROM characters AS character
                    WHERE character.workspace_id = category.workspace_id
                      AND character.category = category.key
                      AND ({ready})
                ) AS character_count
            FROM workspace_categories AS category
            WHERE category.workspace_id = $1::BIGINT
              AND category.is_enabled
            ORDER BY category.sort_order, category.label, category.id
            """,
            int(workspace_id),
        )
        uncategorized = 0
        if include_uncategorized:
            uncategorized = int(
                await connection.fetchval(
                    f"""
                    SELECT COUNT(*)
                    FROM characters AS character
                    WHERE character.workspace_id = $1::BIGINT
                      AND character.category IS NULL
                      AND ({ready})
                    """,
                    int(workspace_id),
                )
                or 0
            )
    result = [
        CategorySummary(
            key=str(row["key"]),
            label=str(row["label"]),
            emoji=str(row["emoji"]),
            character_count=int(row["character_count"] or 0),
        )
        for row in rows
    ]
    if include_uncategorized:
        result.append(
            CategorySummary(
                key="uncategorized",
                label="Без категории",
                emoji="📁",
                character_count=uncategorized,
            )
        )
    if public_only:
        return [item for item in result if item.character_count > 0]
    return result


async def list_workspace_universe_summaries(
    database: Database,
    *,
    workspace_id: int,
    category: str,
    public_only: bool,
    include_unassigned: bool = False,
    include_restricted: bool = True,
) -> list[UniverseSummary]:
    ready = _ready_sql(
        character_alias="character",
        public_only=public_only,
        include_restricted=include_restricted,
    )
    async with database.acquire() as connection:
        category_exists = await connection.fetchval(
            """
            SELECT TRUE
            FROM workspace_categories
            WHERE workspace_id = $1::BIGINT
              AND key = $2::VARCHAR
              AND is_enabled
            """,
            int(workspace_id),
            category,
        )
        if not category_exists:
            raise ValueError("Неизвестная категория архива.")
        rows = await connection.fetch(
            f"""
            SELECT
                universe.key,
                universe.label,
                universe.emoji,
                (
                    SELECT COUNT(*)
                    FROM characters AS character
                    WHERE character.workspace_id = universe.workspace_id
                      AND character.category = $2::VARCHAR
                      AND character.universe = universe.key
                      AND ({ready})
                ) AS character_count
            FROM workspace_universes AS universe
            WHERE universe.workspace_id = $1::BIGINT
              AND universe.is_enabled
            ORDER BY universe.sort_order, universe.label, universe.id
            """,
            int(workspace_id),
            category,
        )
        unassigned = 0
        if include_unassigned:
            unassigned = int(
                await connection.fetchval(
                    f"""
                    SELECT COUNT(*)
                    FROM characters AS character
                    WHERE character.workspace_id = $1::BIGINT
                      AND character.category = $2::VARCHAR
                      AND character.universe IS NULL
                      AND ({ready})
                    """,
                    int(workspace_id),
                    category,
                )
                or 0
            )
    result = [
        UniverseSummary(
            key=str(row["key"]),
            label=str(row["label"]),
            emoji=str(row["emoji"]),
            character_count=int(row["character_count"] or 0),
        )
        for row in rows
    ]
    if include_unassigned:
        result.append(
            UniverseSummary(
                key="unassigned",
                label="Без вселенной",
                emoji="📂",
                character_count=unassigned,
            )
        )
    if public_only:
        return [item for item in result if item.character_count > 0]
    return result


async def list_workspace_story_summaries(
    database: Database,
    *,
    workspace_id: int,
    category: str,
    universe: str,
    public_only: bool,
    include_restricted: bool = True,
) -> list[StorySummary]:
    ready = _ready_sql(
        character_alias="character",
        public_only=public_only,
        include_restricted=include_restricted,
    )
    async with database.acquire() as connection:
        rows = await connection.fetch(
            f"""
            SELECT
                story.id,
                story.universe_key,
                story.key,
                story.short_label,
                story.title,
                story.sort_order,
                COUNT(DISTINCT character.id) FILTER (
                    WHERE character.id IS NOT NULL
                      AND character.workspace_id = $1::BIGINT
                      AND character.category = $2::VARCHAR
                      AND character.universe = $3::VARCHAR
                      AND ({ready})
                ) AS character_count
            FROM workspace_stories AS story
            LEFT JOIN workspace_character_story_links AS link
              ON link.workspace_id = story.workspace_id
             AND link.story_id = story.id
            LEFT JOIN characters AS character
              ON character.workspace_id = link.workspace_id
             AND character.id = link.character_id
            WHERE story.workspace_id = $1::BIGINT
              AND story.universe_key = $3::VARCHAR
              AND story.is_enabled
            GROUP BY story.id
            ORDER BY story.sort_order, story.title, story.id
            """,
            int(workspace_id),
            category,
            universe,
        )
    result = [
        StorySummary(
            id=int(row["id"]),
            universe=str(row["universe_key"]),
            key=str(row["key"]),
            short_label=str(row["short_label"]),
            title=str(row["title"]),
            character_count=int(row["character_count"] or 0),
            release_order=int(row["sort_order"] or 0),
            released_on=None,
            release_precision="unknown",
        )
        for row in rows
    ]
    if public_only:
        return [item for item in result if item.character_count > 0]
    return result


async def list_workspace_character_directory(
    database: Database,
    *,
    workspace_id: int,
    category: str,
    page: int = 0,
    page_size: int = 6,
    public_only: bool,
    universe: str | None = None,
    story_id: int | None = None,
    include_restricted: bool = True,
) -> CharacterDirectoryPage:
    safe_page_size = max(1, min(int(page_size), 10))
    safe_page = max(0, int(page))
    ready = _ready_sql(
        character_alias="character",
        public_only=public_only,
        include_restricted=include_restricted,
    )
    media_count = _media_count_sql(
        character_alias="character",
        public_only=public_only,
        include_restricted=include_restricted,
    )
    category_condition = """
        (($2::VARCHAR = 'uncategorized' AND character.category IS NULL)
         OR character.category = $2::VARCHAR)
    """
    universe_condition = "($3::VARCHAR IS NULL OR character.universe = $3::VARCHAR)"
    story_condition = """
        ($4::BIGINT IS NULL OR EXISTS (
            SELECT 1
            FROM workspace_character_story_links AS selected_link
            WHERE selected_link.workspace_id = character.workspace_id
              AND selected_link.character_id = character.id
              AND selected_link.story_id = $4::BIGINT
        ))
    """
    async with database.acquire() as connection:
        if category != "uncategorized":
            category_exists = await connection.fetchval(
                """
                SELECT TRUE
                FROM workspace_categories
                WHERE workspace_id = $1::BIGINT
                  AND key = $2::VARCHAR
                  AND is_enabled
                """,
                int(workspace_id),
                category,
            )
            if not category_exists:
                raise ValueError("Неизвестная категория архива.")
        if universe is not None:
            universe_exists = await connection.fetchval(
                """
                SELECT TRUE
                FROM workspace_universes
                WHERE workspace_id = $1::BIGINT
                  AND key = $2::VARCHAR
                  AND is_enabled
                """,
                int(workspace_id),
                universe,
            )
            if not universe_exists:
                raise ValueError("Неизвестная вселенная архива.")
        if story_id is not None:
            story_exists = await connection.fetchval(
                """
                SELECT TRUE
                FROM workspace_stories
                WHERE workspace_id = $1::BIGINT
                  AND id = $2::BIGINT
                  AND universe_key = $3::VARCHAR
                  AND is_enabled
                """,
                int(workspace_id),
                int(story_id),
                universe,
            )
            if not story_exists:
                raise ValueError("История не найдена в этом архиве.")

        total = int(
            await connection.fetchval(
                f"""
                SELECT COUNT(*)
                FROM characters AS character
                WHERE character.workspace_id = $1::BIGINT
                  AND {category_condition}
                  AND {universe_condition}
                  AND {story_condition}
                  AND ({ready})
                """,
                int(workspace_id),
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
                character.id,
                character.workspace_id,
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
                primary_story.id AS story_id,
                primary_story.short_label AS story_short_label,
                primary_story.title AS story_title,
                {media_count} AS media_count
            FROM characters AS character
            LEFT JOIN LATERAL (
                SELECT story.id, story.short_label, story.title
                FROM workspace_character_story_links AS link
                JOIN workspace_stories AS story
                  ON story.workspace_id = link.workspace_id
                 AND story.id = link.story_id
                WHERE link.workspace_id = character.workspace_id
                  AND link.character_id = character.id
                  AND story.is_enabled
                ORDER BY
                    link.is_primary DESC,
                    story.sort_order,
                    story.title,
                    story.id
                LIMIT 1
            ) AS primary_story ON TRUE
            WHERE character.workspace_id = $1::BIGINT
              AND {category_condition}
              AND {universe_condition}
              AND {story_condition}
              AND ({ready})
            ORDER BY character.normalized_name, character.id
            OFFSET $5::INTEGER
            LIMIT $6::INTEGER
            """,
            int(workspace_id),
            category,
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
                FROM workspace_stories
                WHERE workspace_id = $1::BIGINT
                  AND id = $2::BIGINT
                  AND universe_key = $3::VARCHAR
                  AND is_enabled
                """,
                int(workspace_id),
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


__all__ = (
    "get_workspace_character_directory_item",
    "list_workspace_category_summaries",
    "list_workspace_character_directory",
    "list_workspace_story_summaries",
    "list_workspace_universe_summaries",
)

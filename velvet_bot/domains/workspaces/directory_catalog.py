from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.database import Database


@dataclass(frozen=True, slots=True)
class WorkspaceDirectoryCategory:
    key: str
    label: str
    emoji: str
    character_count: int


@dataclass(frozen=True, slots=True)
class WorkspaceDirectoryUniverse:
    key: str
    label: str
    emoji: str
    requires_story: bool
    character_count: int


@dataclass(frozen=True, slots=True)
class WorkspaceDirectoryStory:
    id: int
    universe_key: str
    key: str
    short_label: str
    title: str
    character_count: int


@dataclass(frozen=True, slots=True)
class WorkspaceDirectoryCharacter:
    id: int
    workspace_id: int
    name: str
    category_key: str | None
    category_label: str | None
    category_emoji: str | None
    universe_key: str | None
    universe_label: str | None
    universe_emoji: str | None
    primary_story_id: int | None
    primary_story_short_label: str | None
    primary_story_title: str | None
    story_count: int
    media_count: int


@dataclass(frozen=True, slots=True)
class WorkspaceDirectoryPage:
    items: tuple[WorkspaceDirectoryCharacter, ...]
    page: int
    page_size: int
    total_items: int
    category_key: str | None
    universe_key: str | None
    story_id: int | None

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)


async def _require_category(
    database: Database,
    *,
    workspace_id: int,
    category_key: str,
) -> None:
    async with database.acquire() as connection:
        exists = await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM workspace_categories
                WHERE workspace_id = $1::BIGINT
                  AND key = $2::VARCHAR
                  AND is_enabled
            )
            """,
            int(workspace_id),
            category_key,
        )
    if not exists:
        raise ValueError("Категория не найдена в этом пространстве или выключена.")


async def _require_universe(
    database: Database,
    *,
    workspace_id: int,
    universe_key: str,
) -> None:
    async with database.acquire() as connection:
        exists = await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM workspace_universes
                WHERE workspace_id = $1::BIGINT
                  AND key = $2::VARCHAR
                  AND is_enabled
            )
            """,
            int(workspace_id),
            universe_key,
        )
    if not exists:
        raise ValueError("Вселенная не найдена в этом пространстве или выключена.")


async def _require_story(
    database: Database,
    *,
    workspace_id: int,
    story_id: int,
    universe_key: str | None,
) -> None:
    async with database.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT universe_key
            FROM workspace_stories
            WHERE workspace_id = $1::BIGINT
              AND id = $2::BIGINT
              AND is_enabled
            """,
            int(workspace_id),
            int(story_id),
        )
    if row is None:
        raise ValueError("История не найдена в этом пространстве или выключена.")
    if universe_key is not None and str(row["universe_key"]) != universe_key:
        raise ValueError("История не относится к выбранной вселенной.")


async def list_workspace_directory_categories(
    database: Database,
    *,
    workspace_id: int,
    include_uncategorized: bool = True,
) -> tuple[WorkspaceDirectoryCategory, ...]:
    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                wc.key,
                wc.label,
                wc.emoji,
                COUNT(c.id) AS character_count,
                wc.sort_order,
                wc.id
            FROM workspace_categories AS wc
            LEFT JOIN characters AS c
              ON c.workspace_id = wc.workspace_id
             AND c.category = wc.key
            WHERE wc.workspace_id = $1::BIGINT
              AND wc.is_enabled
            GROUP BY wc.id
            ORDER BY wc.sort_order, wc.label, wc.id
            """,
            int(workspace_id),
        )
        uncategorized = 0
        if include_uncategorized:
            uncategorized = int(
                await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM characters
                    WHERE workspace_id = $1::BIGINT
                      AND category IS NULL
                    """,
                    int(workspace_id),
                )
                or 0
            )

    items = [
        WorkspaceDirectoryCategory(
            key=str(row["key"]),
            label=str(row["label"]),
            emoji=str(row["emoji"]),
            character_count=int(row["character_count"] or 0),
        )
        for row in rows
    ]
    if include_uncategorized:
        items.append(
            WorkspaceDirectoryCategory(
                key="uncategorized",
                label="Без категории",
                emoji="🗂",
                character_count=uncategorized,
            )
        )
    return tuple(items)


async def list_workspace_directory_universes(
    database: Database,
    *,
    workspace_id: int,
    category_key: str | None = None,
    include_unassigned: bool = True,
) -> tuple[WorkspaceDirectoryUniverse, ...]:
    if category_key not in {None, "uncategorized"}:
        await _require_category(
            database,
            workspace_id=workspace_id,
            category_key=category_key,
        )

    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                wu.key,
                wu.label,
                wu.emoji,
                wu.requires_story,
                COUNT(c.id) AS character_count,
                wu.sort_order,
                wu.id
            FROM workspace_universes AS wu
            LEFT JOIN characters AS c
              ON c.workspace_id = wu.workspace_id
             AND c.universe = wu.key
             AND (
                    $2::TEXT IS NULL
                    OR ($2::TEXT = 'uncategorized' AND c.category IS NULL)
                    OR c.category = $2::TEXT
                 )
            WHERE wu.workspace_id = $1::BIGINT
              AND wu.is_enabled
            GROUP BY wu.id
            ORDER BY wu.sort_order, wu.label, wu.id
            """,
            int(workspace_id),
            category_key,
        )
        unassigned = 0
        if include_unassigned:
            unassigned = int(
                await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM characters
                    WHERE workspace_id = $1::BIGINT
                      AND universe IS NULL
                      AND (
                            $2::TEXT IS NULL
                            OR ($2::TEXT = 'uncategorized' AND category IS NULL)
                            OR category = $2::TEXT
                          )
                    """,
                    int(workspace_id),
                    category_key,
                )
                or 0
            )

    items = [
        WorkspaceDirectoryUniverse(
            key=str(row["key"]),
            label=str(row["label"]),
            emoji=str(row["emoji"]),
            requires_story=bool(row["requires_story"]),
            character_count=int(row["character_count"] or 0),
        )
        for row in rows
    ]
    if include_unassigned:
        items.append(
            WorkspaceDirectoryUniverse(
                key="unassigned",
                label="Без вселенной",
                emoji="🌐",
                requires_story=False,
                character_count=unassigned,
            )
        )
    return tuple(items)


async def list_workspace_directory_stories(
    database: Database,
    *,
    workspace_id: int,
    universe_key: str,
    category_key: str | None = None,
) -> tuple[WorkspaceDirectoryStory, ...]:
    await _require_universe(
        database,
        workspace_id=workspace_id,
        universe_key=universe_key,
    )
    if category_key not in {None, "uncategorized"}:
        await _require_category(
            database,
            workspace_id=workspace_id,
            category_key=category_key,
        )

    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                ws.id,
                ws.universe_key,
                ws.key,
                ws.short_label,
                ws.title,
                COUNT(DISTINCT csl.character_id) AS character_count
            FROM workspace_stories AS ws
            LEFT JOIN workspace_character_story_links AS csl
              ON csl.workspace_id = ws.workspace_id
             AND csl.story_id = ws.id
            LEFT JOIN characters AS c
              ON c.workspace_id = csl.workspace_id
             AND c.id = csl.character_id
             AND (
                    $3::TEXT IS NULL
                    OR ($3::TEXT = 'uncategorized' AND c.category IS NULL)
                    OR c.category = $3::TEXT
                 )
            WHERE ws.workspace_id = $1::BIGINT
              AND ws.universe_key = $2::VARCHAR
              AND ws.is_enabled
            GROUP BY ws.id
            ORDER BY ws.sort_order, ws.title, ws.id
            """,
            int(workspace_id),
            universe_key,
            category_key,
        )
    return tuple(
        WorkspaceDirectoryStory(
            id=int(row["id"]),
            universe_key=str(row["universe_key"]),
            key=str(row["key"]),
            short_label=str(row["short_label"]),
            title=str(row["title"]),
            character_count=int(row["character_count"] or 0),
        )
        for row in rows
    )


async def list_workspace_directory_characters(
    database: Database,
    *,
    workspace_id: int,
    category_key: str | None = None,
    universe_key: str | None = None,
    story_id: int | None = None,
    page: int = 0,
    page_size: int = 8,
) -> WorkspaceDirectoryPage:
    if category_key not in {None, "uncategorized"}:
        await _require_category(
            database,
            workspace_id=workspace_id,
            category_key=category_key,
        )
    if universe_key not in {None, "unassigned"}:
        await _require_universe(
            database,
            workspace_id=workspace_id,
            universe_key=universe_key,
        )
    if story_id is not None:
        await _require_story(
            database,
            workspace_id=workspace_id,
            story_id=story_id,
            universe_key=(
                universe_key if universe_key not in {None, "unassigned"} else None
            ),
        )

    safe_page = max(0, int(page))
    safe_size = max(1, min(int(page_size), 20))
    category_condition = """
        ($2::TEXT IS NULL
         OR ($2::TEXT = 'uncategorized' AND c.category IS NULL)
         OR c.category = $2::TEXT)
    """
    universe_condition = """
        ($3::TEXT IS NULL
         OR ($3::TEXT = 'unassigned' AND c.universe IS NULL)
         OR c.universe = $3::TEXT)
    """
    story_condition = """
        ($4::BIGINT IS NULL OR EXISTS (
            SELECT 1
            FROM workspace_character_story_links AS selected_link
            WHERE selected_link.workspace_id = c.workspace_id
              AND selected_link.character_id = c.id
              AND selected_link.story_id = $4::BIGINT
        ))
    """

    async with database.acquire() as connection:
        total = int(
            await connection.fetchval(
                f"""
                SELECT COUNT(*)
                FROM characters AS c
                WHERE c.workspace_id = $1::BIGINT
                  AND {category_condition}
                  AND {universe_condition}
                  AND {story_condition}
                """,
                int(workspace_id),
                category_key,
                universe_key,
                story_id,
            )
            or 0
        )
        total_pages = max(1, (total + safe_size - 1) // safe_size)
        normalized_page = min(safe_page, total_pages - 1)
        rows = await connection.fetch(
            f"""
            SELECT
                c.id,
                c.workspace_id,
                c.name,
                c.category AS category_key,
                wc.label AS category_label,
                wc.emoji AS category_emoji,
                c.universe AS universe_key,
                wu.label AS universe_label,
                wu.emoji AS universe_emoji,
                primary_story.id AS primary_story_id,
                primary_story.short_label AS primary_story_short_label,
                primary_story.title AS primary_story_title,
                COUNT(DISTINCT all_story.story_id) AS story_count,
                COUNT(DISTINCT cm.media_id) AS media_count
            FROM characters AS c
            LEFT JOIN workspace_categories AS wc
              ON wc.workspace_id = c.workspace_id
             AND wc.key = c.category
            LEFT JOIN workspace_universes AS wu
              ON wu.workspace_id = c.workspace_id
             AND wu.key = c.universe
            LEFT JOIN workspace_character_story_links AS primary_link
              ON primary_link.workspace_id = c.workspace_id
             AND primary_link.character_id = c.id
             AND primary_link.is_primary
            LEFT JOIN workspace_stories AS primary_story
              ON primary_story.workspace_id = primary_link.workspace_id
             AND primary_story.id = primary_link.story_id
            LEFT JOIN workspace_character_story_links AS all_story
              ON all_story.workspace_id = c.workspace_id
             AND all_story.character_id = c.id
            LEFT JOIN character_media AS cm ON cm.character_id = c.id
            WHERE c.workspace_id = $1::BIGINT
              AND {category_condition}
              AND {universe_condition}
              AND {story_condition}
            GROUP BY c.id, wc.id, wu.id, primary_story.id
            ORDER BY c.normalized_name, c.id
            OFFSET $5::INTEGER
            LIMIT $6::INTEGER
            """,
            int(workspace_id),
            category_key,
            universe_key,
            story_id,
            normalized_page * safe_size,
            safe_size,
        )

    return WorkspaceDirectoryPage(
        items=tuple(
            WorkspaceDirectoryCharacter(
                id=int(row["id"]),
                workspace_id=int(row["workspace_id"]),
                name=str(row["name"]),
                category_key=(
                    str(row["category_key"])
                    if row["category_key"] is not None
                    else None
                ),
                category_label=(
                    str(row["category_label"])
                    if row["category_label"] is not None
                    else None
                ),
                category_emoji=(
                    str(row["category_emoji"])
                    if row["category_emoji"] is not None
                    else None
                ),
                universe_key=(
                    str(row["universe_key"])
                    if row["universe_key"] is not None
                    else None
                ),
                universe_label=(
                    str(row["universe_label"])
                    if row["universe_label"] is not None
                    else None
                ),
                universe_emoji=(
                    str(row["universe_emoji"])
                    if row["universe_emoji"] is not None
                    else None
                ),
                primary_story_id=(
                    int(row["primary_story_id"])
                    if row["primary_story_id"] is not None
                    else None
                ),
                primary_story_short_label=(
                    str(row["primary_story_short_label"])
                    if row["primary_story_short_label"] is not None
                    else None
                ),
                primary_story_title=(
                    str(row["primary_story_title"])
                    if row["primary_story_title"] is not None
                    else None
                ),
                story_count=int(row["story_count"] or 0),
                media_count=int(row["media_count"] or 0),
            )
            for row in rows
        ),
        page=normalized_page,
        page_size=safe_size,
        total_items=total,
        category_key=category_key,
        universe_key=universe_key,
        story_id=story_id,
    )


__all__ = (
    "WorkspaceDirectoryCategory",
    "WorkspaceDirectoryCharacter",
    "WorkspaceDirectoryPage",
    "WorkspaceDirectoryStory",
    "WorkspaceDirectoryUniverse",
    "list_workspace_directory_categories",
    "list_workspace_directory_characters",
    "list_workspace_directory_stories",
    "list_workspace_directory_universes",
)

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


class CharacterDirectoryRepository:
    """PostgreSQL boundary for character directory metadata and filters."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def set_category(self, *, character_id: int, category: str | None) -> None:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                "UPDATE characters SET category = $2::VARCHAR WHERE id = $1::BIGINT",
                int(character_id),
                category,
            )
        if result == "UPDATE 0":
            raise ValueError("Персонаж не найден.")

    async def set_universe(self, *, character_id: int, universe: str | None) -> None:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                current = await connection.fetchrow(
                    "SELECT universe FROM characters WHERE id = $1::BIGINT FOR UPDATE",
                    int(character_id),
                )
                if current is None:
                    raise ValueError("Персонаж не найден.")
                if current["universe"] != universe:
                    await connection.execute(
                        "DELETE FROM character_story_links WHERE character_id = $1::BIGINT",
                        int(character_id),
                    )
                    await connection.execute(
                        """
                        UPDATE characters
                        SET universe = $2::VARCHAR, story_id = NULL
                        WHERE id = $1::BIGINT
                        """,
                        int(character_id),
                        universe,
                    )
                else:
                    await connection.execute(
                        "UPDATE characters SET universe = $2::VARCHAR WHERE id = $1::BIGINT",
                        int(character_id),
                        universe,
                    )

    async def set_prompt_url(
        self,
        *,
        character_id: int,
        prompt_post_url: str | None,
    ) -> None:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE characters
                SET prompt_post_url = $2::TEXT
                WHERE id = $1::BIGINT
                """,
                int(character_id),
                prompt_post_url,
            )
        if result == "UPDATE 0":
            raise ValueError("Персонаж не найден.")

    async def get_item(self, character_id: int) -> CharacterDirectoryItem | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    c.id, c.name, c.created_by, c.created_in_chat, c.created_at,
                    c.archive_chat_id, c.archive_thread_id, c.archive_topic_url,
                    c.category, c.universe, c.prompt_post_url, c.story_id,
                    s.short_label AS story_short_label,
                    s.title AS story_title,
                    COUNT(cm.media_id) AS media_count
                FROM characters AS c
                LEFT JOIN character_stories AS s ON s.id = c.story_id
                LEFT JOIN character_media AS cm ON cm.character_id = c.id
                WHERE c.id = $1::BIGINT
                GROUP BY c.id, s.id
                """,
                int(character_id),
            )
        return self._row_to_directory_item(row) if row is not None else None

    async def list_category_summaries(
        self,
        *,
        public_only: bool,
        include_uncategorized: bool = False,
    ) -> tuple[CategorySummary, ...]:
        keys = list(CATEGORY_ORDER)
        if include_uncategorized:
            keys.append("uncategorized")

        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT
                    COALESCE(c.category, 'uncategorized') AS category,
                    COUNT(DISTINCT c.id) AS character_count
                FROM characters AS c
                LEFT JOIN character_media AS cm ON cm.character_id = c.id
                WHERE (
                    $1::BOOLEAN = FALSE
                    OR (
                        cm.media_id IS NOT NULL
                        AND c.universe IS NOT NULL
                        AND (
                            c.universe NOT IN {STORY_REQUIRED_SQL}
                            OR EXISTS (
                                SELECT 1
                                FROM character_story_links AS ready_link
                                WHERE ready_link.character_id = c.id
                            )
                        )
                    )
                )
                GROUP BY COALESCE(c.category, 'uncategorized')
                """,
                bool(public_only),
            )
        counts = {
            str(row["category"]): int(row["character_count"] or 0)
            for row in rows
        }
        return tuple(
            CategorySummary(
                key=key,
                label=CATEGORY_LABELS[key],
                emoji=CATEGORY_EMOJI[key],
                character_count=counts.get(key, 0),
            )
            for key in keys
        )

    async def list_universe_summaries(
        self,
        *,
        category: str,
        public_only: bool,
        include_unassigned: bool = False,
    ) -> tuple[UniverseSummary, ...]:
        keys = list(UNIVERSE_ORDER)
        if include_unassigned:
            keys.append("unassigned")

        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT
                    COALESCE(c.universe, 'unassigned') AS universe,
                    COUNT(DISTINCT c.id) AS character_count
                FROM characters AS c
                LEFT JOIN character_media AS cm ON cm.character_id = c.id
                WHERE c.category = $1::VARCHAR
                  AND (
                        $2::BOOLEAN = FALSE
                        OR (
                            cm.media_id IS NOT NULL
                            AND (
                                c.universe NOT IN {STORY_REQUIRED_SQL}
                                OR EXISTS (
                                SELECT 1
                                FROM character_story_links AS ready_link
                                WHERE ready_link.character_id = c.id
                            )
                            )
                        )
                      )
                GROUP BY COALESCE(c.universe, 'unassigned')
                """,
                category,
                bool(public_only),
            )
        counts = {
            str(row["universe"]): int(row["character_count"] or 0)
            for row in rows
        }
        return tuple(
            UniverseSummary(
                key=key,
                label=UNIVERSE_LABELS[key],
                emoji=UNIVERSE_EMOJI[key],
                character_count=counts.get(key, 0),
            )
            for key in keys
        )

    async def list_directory(
        self,
        *,
        category: str,
        page: int = 0,
        page_size: int = 6,
        public_only: bool,
        universe: str | None = None,
        story_id: int | None = None,
    ) -> CharacterDirectoryPage:
        safe_page_size = max(1, min(int(page_size), 10))
        safe_page = max(0, int(page))
        category_condition = """
            (($1::TEXT = 'uncategorized' AND c.category IS NULL) OR c.category = $1)
        """
        universe_condition = "($3::TEXT IS NULL OR c.universe = $3)"
        story_condition = """
            ($4::BIGINT IS NULL OR EXISTS (
                SELECT 1
                FROM character_story_links AS selected_link
                WHERE selected_link.character_id = c.id
                  AND selected_link.story_id = $4::BIGINT
            ))
        """
        public_condition = f"""
            (
                $2::BOOLEAN = FALSE
                OR (
                    cm.media_id IS NOT NULL
                    AND c.universe IS NOT NULL
                    AND (
                        c.universe NOT IN {STORY_REQUIRED_SQL}
                        OR EXISTS (
                                SELECT 1
                                FROM character_story_links AS ready_link
                                WHERE ready_link.character_id = c.id
                            )
                    )
                )
            )
        """

        async with self._database.acquire() as connection:
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
                    ) AS directory
                    """,
                    category,
                    bool(public_only),
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
                LEFT JOIN character_media AS cm ON cm.character_id = c.id
                WHERE {category_condition}
                  AND {public_condition}
                  AND {universe_condition}
                  AND {story_condition}
                GROUP BY c.id, s.id
                ORDER BY c.normalized_name ASC, c.id ASC
                OFFSET $5::INTEGER
                LIMIT $6::INTEGER
                """,
                category,
                bool(public_only),
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
                    WHERE id = $1::BIGINT AND universe = $2::VARCHAR
                    """,
                    int(story_id),
                    universe,
                )

        return CharacterDirectoryPage(
            items=tuple(self._row_to_directory_item(row) for row in rows),
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

    @staticmethod
    def _row_to_character(row) -> CharacterRecord:
        return CharacterRecord(
            id=int(row["id"]),
            name=str(row["name"]),
            created_by=row["created_by"],
            created_in_chat=row["created_in_chat"],
            created_at=row["created_at"],
            archive_chat_id=row["archive_chat_id"],
            archive_thread_id=row["archive_thread_id"],
            archive_topic_url=row["archive_topic_url"],
        )

    @classmethod
    def _row_to_directory_item(cls, row) -> CharacterDirectoryItem:
        return CharacterDirectoryItem(
            character=cls._row_to_character(row),
            category=row["category"],
            prompt_post_url=row["prompt_post_url"],
            media_count=int(row["media_count"] or 0),
            universe=row["universe"],
            story_id=(int(row["story_id"]) if row["story_id"] is not None else None),
            story_short_label=row["story_short_label"],
            story_title=row["story_title"],
        )


__all__ = ("CharacterDirectoryRepository",)

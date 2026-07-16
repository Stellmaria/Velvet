from __future__ import annotations

from datetime import date

from velvet_bot.database import Database
from velvet_bot.domains.stories.models import CharacterStory, StoryPage, StorySummary

_STORY_COLUMNS = """
    id,
    universe,
    key,
    short_label,
    title,
    sort_order,
    release_order,
    released_on,
    release_precision
"""


class StoryRepository:
    """PostgreSQL boundary for story catalog and character assignments."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def get(self, story_id: int) -> CharacterStory | None:
        async with self._database._require_pool().acquire() as connection:
            row = await connection.fetchrow(
                f"""
                SELECT {_STORY_COLUMNS}
                FROM character_stories
                WHERE id = $1::BIGINT
                """,
                int(story_id),
            )
        return self._row_to_story(row) if row is not None else None

    async def list(self, *, universe: str) -> list[CharacterStory]:
        async with self._database._require_pool().acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT {_STORY_COLUMNS}
                FROM character_stories
                WHERE universe = $1::VARCHAR
                ORDER BY
                    release_order DESC,
                    released_on DESC NULLS LAST,
                    title,
                    id
                """,
                universe,
            )
        return [self._row_to_story(row) for row in rows]

    async def list_page(
        self,
        *,
        universe: str,
        page: int = 0,
        page_size: int = 7,
    ) -> StoryPage:
        safe_page_size = max(1, min(int(page_size), 8))
        safe_page = max(0, int(page))
        async with self._database._require_pool().acquire() as connection:
            total = int(
                await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM character_stories
                    WHERE universe = $1::VARCHAR
                    """,
                    universe,
                )
                or 0
            )
            total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
            normalized_page = min(safe_page, total_pages - 1)
            rows = await connection.fetch(
                f"""
                SELECT {_STORY_COLUMNS}
                FROM character_stories
                WHERE universe = $1::VARCHAR
                ORDER BY
                    release_order DESC,
                    released_on DESC NULLS LAST,
                    title,
                    id
                OFFSET $2::INTEGER
                LIMIT $3::INTEGER
                """,
                universe,
                normalized_page * safe_page_size,
                safe_page_size,
            )
        return StoryPage(
            items=[self._row_to_story(row) for row in rows],
            universe=universe,
            page=normalized_page,
            page_size=safe_page_size,
            total_stories=total,
        )

    async def find(self, *, universe: str, value: str) -> CharacterStory | None:
        async with self._database._require_pool().acquire() as connection:
            row = await connection.fetchrow(
                f"""
                SELECT {_STORY_COLUMNS}
                FROM character_stories
                WHERE universe = $1::VARCHAR
                  AND (
                        LOWER(short_label) = LOWER($2::TEXT)
                        OR LOWER(key) = LOWER($2::TEXT)
                        OR LOWER(title) = LOWER($2::TEXT)
                      )
                ORDER BY release_order DESC, id
                LIMIT 1
                """,
                universe,
                value,
            )
        return self._row_to_story(row) if row is not None else None

    async def create(
        self,
        *,
        universe: str,
        key: str,
        short_label: str,
        title: str,
        released_on: date | None,
        release_precision: str,
    ) -> CharacterStory:
        async with self._database._require_pool().acquire() as connection:
            row = await connection.fetchrow(
                f"""
                INSERT INTO character_stories (
                    universe,
                    key,
                    short_label,
                    title,
                    sort_order,
                    release_order,
                    released_on,
                    release_precision
                )
                VALUES (
                    $1::VARCHAR,
                    $2::VARCHAR,
                    $3::VARCHAR,
                    $4::VARCHAR,
                    COALESCE(
                        (
                            SELECT MAX(release_order) + 10
                            FROM character_stories
                            WHERE universe = $1::VARCHAR
                        ),
                        10
                    ),
                    COALESCE(
                        (
                            SELECT MAX(release_order) + 10
                            FROM character_stories
                            WHERE universe = $1::VARCHAR
                        ),
                        10
                    ),
                    $5::DATE,
                    $6::VARCHAR
                )
                ON CONFLICT (universe, key) DO UPDATE
                SET short_label = EXCLUDED.short_label,
                    title = EXCLUDED.title,
                    released_on = COALESCE(
                        EXCLUDED.released_on,
                        character_stories.released_on
                    ),
                    release_precision = CASE
                        WHEN EXCLUDED.released_on IS NULL
                        THEN character_stories.release_precision
                        ELSE EXCLUDED.release_precision
                    END
                RETURNING {_STORY_COLUMNS}
                """,
                universe,
                key,
                short_label,
                title,
                released_on,
                release_precision,
            )
        if row is None:
            raise RuntimeError("Не удалось сохранить историю.")
        return self._row_to_story(row)

    async def set_character_story(
        self,
        *,
        character_id: int,
        story_id: int | None,
    ) -> None:
        async with self._database._require_pool().acquire() as connection:
            if story_id is None:
                result = await connection.execute(
                    """
                    UPDATE characters
                    SET story_id = NULL
                    WHERE id = $1::BIGINT
                    """,
                    int(character_id),
                )
            else:
                result = await connection.execute(
                    """
                    UPDATE characters AS c
                    SET story_id = s.id
                    FROM character_stories AS s
                    WHERE c.id = $1::BIGINT
                      AND s.id = $2::BIGINT
                      AND c.universe = s.universe
                    """,
                    int(character_id),
                    int(story_id),
                )
        if result == "UPDATE 0":
            raise ValueError(
                "Персонаж не найден или история относится к другой вселенной."
            )

    async def list_summaries(
        self,
        *,
        category: str,
        universe: str,
        public_only: bool,
    ) -> list[StorySummary]:
        async with self._database._require_pool().acquire() as connection:
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
                    COUNT(DISTINCT c.id) FILTER (
                        WHERE c.category = $1::VARCHAR
                          AND c.universe = $2::VARCHAR
                          AND (
                                $3::BOOLEAN = FALSE
                                OR cm.media_id IS NOT NULL
                              )
                    ) AS character_count
                FROM character_stories AS s
                LEFT JOIN characters AS c ON c.story_id = s.id
                LEFT JOIN character_media AS cm ON cm.character_id = c.id
                WHERE s.universe = $2::VARCHAR
                GROUP BY s.id
                ORDER BY
                    s.release_order DESC,
                    s.released_on DESC NULLS LAST,
                    s.title,
                    s.id
                """,
                category,
                universe,
                bool(public_only),
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
        if public_only:
            return [item for item in summaries if item.character_count > 0]
        return summaries

    @staticmethod
    def _row_to_story(row) -> CharacterStory:
        return CharacterStory(
            id=int(row["id"]),
            universe=str(row["universe"]),
            key=str(row["key"]),
            short_label=str(row["short_label"]),
            title=str(row["title"]),
            sort_order=int(row["sort_order"] or 0),
            release_order=int(row["release_order"] or 0),
            released_on=row["released_on"],
            release_precision=str(row["release_precision"] or "unknown"),
        )


__all__ = ("StoryRepository",)

from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.stories.models import StorySummary
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID


class PublicStoryCatalog:
    """Read public story filters using only characters from one workspace."""

    def __init__(
        self,
        database: Database,
        *,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> None:
        self._database = database
        self._workspace_id = int(workspace_id)

    async def list_summaries(
        self,
        *,
        category: str,
        universe: str,
        public_only: bool,
    ) -> list[StorySummary]:
        async with self._database.acquire() as connection:
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
                        WHERE c.workspace_id = $1::BIGINT
                          AND c.category = $2::VARCHAR
                          AND c.universe = $3::VARCHAR
                          AND (
                                $4::BOOLEAN = FALSE
                                OR cm.media_id IS NOT NULL
                              )
                    ) AS character_count
                FROM character_stories AS s
                LEFT JOIN character_story_links AS link ON link.story_id = s.id
                LEFT JOIN characters AS c ON c.id = link.character_id
                LEFT JOIN character_media AS cm ON cm.character_id = c.id
                WHERE s.universe = $3::VARCHAR
                GROUP BY s.id
                ORDER BY
                    s.release_order DESC,
                    s.released_on DESC NULLS LAST,
                    s.title,
                    s.id
                """,
                self._workspace_id,
                category,
                universe,
                bool(public_only),
            )
        items = [
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
            return [item for item in items if item.character_count > 0]
        return items


__all__ = ("PublicStoryCatalog",)

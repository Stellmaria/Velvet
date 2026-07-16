from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.multi_story_support import AssignedCharacterStory
from velvet_bot.story_catalog import CharacterStory


async def list_assigned_character_stories(
    database: Database,
    *,
    character_id: int,
) -> list[AssignedCharacterStory]:
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                story.id,
                story.universe,
                story.key,
                story.short_label,
                story.title,
                story.sort_order,
                story.release_order,
                story.released_on,
                story.release_precision,
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
            """,
            character_id,
        )
    return [
        AssignedCharacterStory(
            story=CharacterStory(
                id=int(row["id"]),
                universe=str(row["universe"]),
                key=str(row["key"]),
                short_label=str(row["short_label"]),
                title=str(row["title"]),
                sort_order=int(row["sort_order"] or 0),
                release_order=int(row["release_order"] or 0),
                released_on=row["released_on"],
                release_precision=str(row["release_precision"] or "unknown"),
            ),
            is_primary=bool(row["is_primary"]),
        )
        for row in rows
    ]

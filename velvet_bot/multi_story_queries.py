from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.stories import AssignedCharacterStory, StoryRepository


async def list_assigned_character_stories(
    database: Database,
    *,
    character_id: int,
) -> list[AssignedCharacterStory]:
    return await StoryRepository(database).list_assigned_character_stories(
        character_id=character_id
    )


__all__ = ("list_assigned_character_stories",)

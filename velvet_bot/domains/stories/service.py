from __future__ import annotations

import unicodedata
from datetime import date

from velvet_bot.domains.stories.catalog import (
    clean_story_short_label,
    clean_story_title,
    make_story_key,
)
from velvet_bot.domains.stories.constants import KNOWN_UNIVERSES, RELEASE_PRECISIONS
from velvet_bot.domains.stories.models import CharacterStory, StoryPage, StorySummary
from velvet_bot.domains.stories.repository import StoryRepository


class StoryService:
    """Validate story catalog operations and coordinate persistence."""

    def __init__(self, repository: StoryRepository) -> None:
        self._repository = repository

    @staticmethod
    def validate_universe(universe: str) -> str:
        if universe not in KNOWN_UNIVERSES:
            raise ValueError("Неизвестная вселенная.")
        return universe

    async def get(self, story_id: int) -> CharacterStory | None:
        return await self._repository.get(story_id)

    async def list(self, *, universe: str) -> list[CharacterStory]:
        return await self._repository.list(universe=self.validate_universe(universe))

    async def list_page(
        self,
        *,
        universe: str,
        page: int = 0,
        page_size: int = 7,
    ) -> StoryPage:
        return await self._repository.list_page(
            universe=self.validate_universe(universe),
            page=page,
            page_size=page_size,
        )

    async def find(self, *, universe: str, value: str) -> CharacterStory | None:
        cleaned = " ".join(unicodedata.normalize("NFKC", value).split())
        if not cleaned:
            return None
        return await self._repository.find(
            universe=self.validate_universe(universe),
            value=cleaned,
        )

    async def create(
        self,
        *,
        universe: str,
        short_label: str,
        title: str,
        released_on: date | None = None,
        release_precision: str = "unknown",
    ) -> CharacterStory:
        self.validate_universe(universe)
        if release_precision not in RELEASE_PRECISIONS:
            raise ValueError("Неизвестная точность даты выхода.")
        if released_on is None:
            release_precision = "unknown"
        cleaned_short = clean_story_short_label(short_label)
        cleaned_title = clean_story_title(title)
        return await self._repository.create(
            universe=universe,
            key=make_story_key(cleaned_short),
            short_label=cleaned_short,
            title=cleaned_title,
            released_on=released_on,
            release_precision=release_precision,
        )

    async def set_character_story(
        self,
        *,
        character_id: int,
        story_id: int | None,
    ) -> None:
        await self._repository.set_character_story(
            character_id=character_id,
            story_id=story_id,
        )

    async def list_summaries(
        self,
        *,
        category: str,
        universe: str,
        public_only: bool,
    ) -> list[StorySummary]:
        return await self._repository.list_summaries(
            category=category,
            universe=self.validate_universe(universe),
            public_only=public_only,
        )


__all__ = ("StoryService",)

from __future__ import annotations

from velvet_bot.domains.characters.catalog import (
    normalize_category,
    normalize_universe,
    validate_prompt_post_url,
)
from velvet_bot.domains.characters.constants import (
    CATEGORY_ORDER,
    UNIVERSE_VALUE_ORDER,
)
from velvet_bot.domains.characters.models import (
    CategorySummary,
    CharacterDirectoryItem,
    CharacterDirectoryPage,
    UniverseSummary,
)
from velvet_bot.domains.characters.repository import CharacterDirectoryRepository


class CharacterDirectoryService:
    """Validate character filters and coordinate directory persistence."""

    def __init__(self, repository: CharacterDirectoryRepository) -> None:
        self._repository = repository

    async def set_category(
        self,
        *,
        character_id: int,
        category: str | None,
    ) -> None:
        if category is not None and category not in CATEGORY_ORDER:
            raise ValueError("Неизвестная категория архива.")
        await self._repository.set_category(
            character_id=character_id,
            category=category,
        )

    async def set_category_from_text(
        self,
        *,
        character_id: int,
        value: str,
        allow_uncategorized: bool = False,
    ) -> str | None:
        category = normalize_category(
            value,
            allow_uncategorized=allow_uncategorized,
        )
        stored = None if category == "uncategorized" else category
        await self.set_category(character_id=character_id, category=stored)
        return stored

    async def set_universe(
        self,
        *,
        character_id: int,
        universe: str | None,
    ) -> None:
        if universe is not None and universe not in UNIVERSE_VALUE_ORDER:
            raise ValueError("Неизвестная вселенная архива.")
        await self._repository.set_universe(
            character_id=character_id,
            universe=universe,
        )

    async def set_universe_from_text(
        self,
        *,
        character_id: int,
        value: str,
        allow_unassigned: bool = False,
    ) -> str | None:
        universe = normalize_universe(
            value,
            allow_unassigned=allow_unassigned,
        )
        stored = None if universe == "unassigned" else universe
        await self.set_universe(character_id=character_id, universe=stored)
        return stored

    async def set_prompt_url(
        self,
        *,
        character_id: int,
        prompt_post_url: str | None,
    ) -> None:
        cleaned = (
            validate_prompt_post_url(prompt_post_url)
            if prompt_post_url is not None
            else None
        )
        await self._repository.set_prompt_url(
            character_id=character_id,
            prompt_post_url=cleaned,
        )

    async def get_item(self, character_id: int) -> CharacterDirectoryItem | None:
        return await self._repository.get_item(character_id)

    async def list_category_summaries(
        self,
        *,
        public_only: bool,
        include_uncategorized: bool = False,
    ) -> tuple[CategorySummary, ...]:
        return await self._repository.list_category_summaries(
            public_only=public_only,
            include_uncategorized=include_uncategorized,
        )

    async def list_universe_summaries(
        self,
        *,
        category: str,
        public_only: bool,
        include_unassigned: bool = False,
    ) -> tuple[UniverseSummary, ...]:
        try:
            normalized_category = normalize_category(
                category,
                allow_uncategorized=False,
            )
        except ValueError as error:
            raise ValueError("Неизвестная категория архива.") from error
        return await self._repository.list_universe_summaries(
            category=normalized_category,
            public_only=public_only,
            include_unassigned=include_unassigned,
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
        try:
            normalized_category = normalize_category(
                category,
                allow_uncategorized=True,
            )
        except ValueError as error:
            raise ValueError("Неизвестная категория архива.") from error
        if universe is not None and universe not in UNIVERSE_VALUE_ORDER:
            raise ValueError("Неизвестная вселенная архива.")
        if normalized_category == "uncategorized" and universe is not None:
            raise ValueError(
                "Для раздела без категории фильтр вселенной недоступен."
            )
        if story_id is not None and universe is None:
            raise ValueError("Для фильтра по истории сначала нужна вселенная.")
        return await self._repository.list_directory(
            category=normalized_category,
            page=page,
            page_size=page_size,
            public_only=public_only,
            universe=universe,
            story_id=story_id,
        )


__all__ = ("CharacterDirectoryService",)

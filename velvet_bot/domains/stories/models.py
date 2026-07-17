from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class CharacterStory:
    id: int
    universe: str
    key: str
    short_label: str
    title: str
    sort_order: int
    release_order: int = 0
    released_on: date | None = None
    release_precision: str = "unknown"


@dataclass(frozen=True, slots=True)
class AssignedCharacterStory:
    story: CharacterStory
    is_primary: bool


@dataclass(frozen=True, slots=True)
class StorySummary:
    id: int
    universe: str
    key: str
    short_label: str
    title: str
    character_count: int
    release_order: int = 0
    released_on: date | None = None
    release_precision: str = "unknown"


@dataclass(frozen=True, slots=True)
class StoryPage:
    items: list[CharacterStory]
    universe: str
    page: int
    page_size: int
    total_stories: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_stories + self.page_size - 1) // self.page_size)


__all__ = ("AssignedCharacterStory", "CharacterStory", "StoryPage", "StorySummary")

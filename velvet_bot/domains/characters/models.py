from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CharacterRecord:
    id: int
    name: str
    created_by: int | None
    created_in_chat: int | None
    created_at: datetime
    archive_chat_id: int | None
    archive_thread_id: int | None
    archive_topic_url: str | None


@dataclass(frozen=True, slots=True)
class CategorySummary:
    key: str
    label: str
    emoji: str
    character_count: int


@dataclass(frozen=True, slots=True)
class UniverseSummary:
    key: str
    label: str
    emoji: str
    character_count: int


@dataclass(frozen=True, slots=True)
class CharacterDirectoryItem:
    character: CharacterRecord
    category: str | None
    prompt_post_url: str | None
    media_count: int
    universe: str | None = None
    story_id: int | None = None
    story_short_label: str | None = None
    story_title: str | None = None


@dataclass(frozen=True, slots=True)
class CharacterDirectoryPage:
    items: tuple[CharacterDirectoryItem, ...]
    category: str
    page: int
    page_size: int
    total_characters: int
    universe: str | None = None
    story_id: int | None = None
    story_short_label: str | None = None
    story_title: str | None = None

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_characters + self.page_size - 1) // self.page_size)


__all__ = (
    "CategorySummary",
    "CharacterDirectoryItem",
    "CharacterDirectoryPage",
    "CharacterRecord",
    "UniverseSummary",
)

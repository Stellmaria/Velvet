from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class DiscussionSummary:
    discussion_chat_id: int
    parent_channel_id: int
    linked_threads: int
    total_comments: int
    unique_participants: int
    total_comment_reactions: int
    published_publications: int
    publications_without_comments: int
    average_comments_per_publication: float
    first_comment_at: datetime | None
    last_comment_at: datetime | None


@dataclass(frozen=True, slots=True)
class DiscussedPost:
    post_id: int
    publication_key: str
    posted_at: datetime
    text_content: str
    message_url: str | None
    view_count: int
    channel_reactions: int
    comment_count: int
    first_comment_seconds: int | None
    unique_participants: int
    comment_reactions: int


@dataclass(frozen=True, slots=True)
class DiscussedPostPage:
    items: list[DiscussedPost]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)


@dataclass(frozen=True, slots=True)
class ActivityBreakdown:
    weekdays: tuple[int, ...]
    hours: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ActivitySpike:
    day: date
    comment_count: int
    baseline: float
    ratio: float


@dataclass(frozen=True, slots=True)
class RelinkResult:
    roots_marked: int
    comments_linked: int
    threads_linked: int


__all__ = (
    "ActivityBreakdown",
    "ActivitySpike",
    "DiscussedPost",
    "DiscussedPostPage",
    "DiscussionSummary",
    "RelinkResult",
)

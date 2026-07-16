from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class PublicationIssue:
    code: str
    severity: str
    title: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class PublicationItem:
    id: int
    draft_id: int
    position: int
    telegram_file_id: str
    telegram_file_unique_id: str | None
    media_type: str
    mime_type: str | None
    file_name: str | None
    file_size: int | None
    source_message_id: int | None
    has_spoiler: bool


@dataclass(frozen=True, slots=True)
class PublicationDraft:
    id: int
    owner_id: int
    target_chat_id: int
    source_chat_id: int | None
    source_message_id: int | None
    source_media_group_id: str | None
    text_content: str
    status: str
    post_type: str
    has_spoiler: bool
    content_hash: str
    validation_status: str
    validation_error_count: int
    validation_warning_count: int
    validation_report: tuple[PublicationIssue, ...]
    scheduled_at: datetime | None
    published_at: datetime | None
    published_message_ids: tuple[int, ...]
    attempt_count: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    items: tuple[PublicationItem, ...]


@dataclass(frozen=True, slots=True)
class PublicationDraftPage:
    items: tuple[PublicationDraft, ...]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)


@dataclass(frozen=True, slots=True)
class PublicationInboxPayload:
    owner_id: int
    source_chat_id: int
    source_message_id: int
    media_group_id: str | None
    text_content: str
    telegram_file_id: str | None
    telegram_file_unique_id: str | None
    media_type: str
    mime_type: str | None
    file_name: str | None
    file_size: int | None
    has_spoiler: bool


@dataclass(frozen=True, slots=True)
class PublicationInboxItem:
    id: int
    payload: PublicationInboxPayload


@dataclass(frozen=True, slots=True)
class PublicationCharacterInfo:
    id: int
    name: str
    category: str | None
    universe: str | None
    story_id: int | None
    has_multi_story: bool
    normalized_alias: str


@dataclass(frozen=True, slots=True)
class DuplicateDraftInfo:
    id: int
    status: str


@dataclass(frozen=True, slots=True)
class DuplicatePostInfo:
    message_id: int
    message_url: str | None


@dataclass(frozen=True, slots=True)
class PublicationValidationContext:
    characters: tuple[PublicationCharacterInfo, ...]
    duplicate_draft: DuplicateDraftInfo | None
    duplicate_post: DuplicatePostInfo | None


__all__ = (
    "DuplicateDraftInfo",
    "DuplicatePostInfo",
    "PublicationCharacterInfo",
    "PublicationDraft",
    "PublicationDraftPage",
    "PublicationInboxItem",
    "PublicationInboxPayload",
    "PublicationIssue",
    "PublicationItem",
    "PublicationValidationContext",
)

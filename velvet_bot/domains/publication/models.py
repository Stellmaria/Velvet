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


__all__ = (
    "PublicationDraft",
    "PublicationDraftPage",
    "PublicationIssue",
    "PublicationItem",
)

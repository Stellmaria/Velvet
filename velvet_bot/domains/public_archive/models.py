from __future__ import annotations

from dataclasses import dataclass

PUBLIC_ARCHIVE_REVIEWER_ID = 7221553045


@dataclass(frozen=True, slots=True)
class PublicMediaState:
    like_count: int
    liked_by_user: bool
    subscribed: bool
    subscriber_count: int = 0
    view_count: int = 0
    download_count: int = 0
    reviewed_by_owner: bool = False
    watermark_applied: bool = False
    watermark_approved: bool = False


@dataclass(frozen=True, slots=True)
class PublicDownloadSource:
    telegram_file_id: str
    variant: str


@dataclass(frozen=True, slots=True)
class LikeToggleResult:
    liked: bool
    like_count: int


@dataclass(frozen=True, slots=True)
class PendingPublicNotification:
    workspace_id: int
    character_id: int
    character_name: str
    media_id: int
    user_id: int


__all__ = (
    "LikeToggleResult",
    "PendingPublicNotification",
    "PUBLIC_ARCHIVE_REVIEWER_ID",
    "PublicDownloadSource",
    "PublicMediaState",
)

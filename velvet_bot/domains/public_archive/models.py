from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PublicMediaState:
    like_count: int
    liked_by_user: bool
    subscribed: bool
    subscriber_count: int = 0


@dataclass(frozen=True, slots=True)
class LikeToggleResult:
    liked: bool
    like_count: int


@dataclass(frozen=True, slots=True)
class PendingPublicNotification:
    character_id: int
    character_name: str
    media_id: int
    user_id: int


__all__ = (
    "LikeToggleResult",
    "PendingPublicNotification",
    "PublicMediaState",
)

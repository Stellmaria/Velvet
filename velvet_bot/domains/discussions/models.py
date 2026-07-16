from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DiscussionOverview:
    chat_id: int
    parent_channel_id: int | None
    chat_title: str | None
    chat_username: str | None
    total_messages: int
    root_posts: int
    replies: int
    participant_count: int
    reactions_total: int
    first_message_at: datetime | None
    last_message_at: datetime | None


@dataclass(frozen=True, slots=True)
class ParticipantStat:
    user_id: int | None
    display_name: str
    username: str | None
    message_count: int
    reply_count: int
    reactions_received: int
    last_message_at: datetime | None


__all__ = ("DiscussionOverview", "ParticipantStat")

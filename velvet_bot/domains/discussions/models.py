from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DiscussionOverview:
    chat_id: int
    total_messages: int
    total_publications: int
    unique_participants: int
    reply_messages: int
    media_messages: int
    spoiler_messages: int
    prompt_messages: int
    total_hashtag_uses: int
    unique_hashtags: int
    total_reactions: int
    first_message_at: datetime | None
    last_message_at: datetime | None


@dataclass(frozen=True, slots=True)
class ParticipantStat:
    sender_id: str
    sender_name: str
    message_count: int
    reply_count: int
    media_count: int
    hashtag_count: int
    last_message_at: datetime | None


__all__ = ("DiscussionOverview", "ParticipantStat")

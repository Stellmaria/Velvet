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


@dataclass(frozen=True, slots=True)
class DiscussionMessageEvent:
    chat_id: int
    chat_title: str | None
    chat_username: str | None
    message_id: int
    posted_at: datetime
    edited_at: datetime | None
    sender_is_bot: bool
    sender_id: str | None
    sender_name: str | None
    text_content: str
    media_group_id: str | None
    media_type: str
    has_spoiler: bool
    reply_to_message_id: int | None
    reply_text: str
    reply_date: datetime | None
    reply_is_automatic_forward: bool
    topic_id: int | None
    is_automatic_forward: bool
    forward_channel_id: int | None
    forward_message_id: int | None


@dataclass(frozen=True, slots=True)
class DiscussionIngestResult:
    stored: bool
    parent_channel_id: int | None
    root_message_id: int | None
    source_channel_message_id: int | None


__all__ = (
    "DiscussionIngestResult",
    "DiscussionMessageEvent",
    "DiscussionOverview",
    "ParticipantStat",
)

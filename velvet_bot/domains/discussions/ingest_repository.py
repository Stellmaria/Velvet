from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.discussions.models import DiscussionMessageEvent


class DiscussionIngestRepository:
    """PostgreSQL boundary for live discussion message ingestion."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def get_parent_channel_id(self, discussion_chat_id: int) -> int | None:
        async with self._database._require_pool().acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT parent_channel_id
                FROM tracked_channels
                WHERE channel_id = $1::BIGINT
                  AND channel_type = 'discussion'
                """,
                int(discussion_chat_id),
            )
        return int(value) if value is not None else None

    async def resolve_root_reference(
        self,
        *,
        discussion_chat_id: int,
        message_id: int,
    ) -> tuple[int | None, int | None]:
        async with self._database._require_pool().acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT root_channel_id, root_message_id
                FROM channel_posts
                WHERE channel_id = $1::BIGINT
                  AND message_id = $2::BIGINT
                  AND source_type = 'discussion'
                """,
                int(discussion_chat_id),
                int(message_id),
            )
        if row is None:
            return None, None
        return row["root_channel_id"], row["root_message_id"]

    async def match_autoforwarded_post(
        self,
        *,
        event: DiscussionMessageEvent,
        parent_channel_id: int,
    ) -> tuple[int | None, int | None]:
        linked_channel_id = event.forward_channel_id or parent_channel_id
        linked_message_id = event.forward_message_id
        if linked_message_id is None:
            return None, None

        async with self._database._require_pool().acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT channel_id, message_id
                FROM channel_posts
                WHERE channel_id = $1::BIGINT
                  AND message_id = $2::BIGINT
                  AND source_type = 'channel'
                """,
                int(linked_channel_id),
                int(linked_message_id),
            )
            if row is None:
                return None, None
            await connection.execute(
                """
                UPDATE channel_posts
                SET linked_discussion_chat_id = $3::BIGINT,
                    linked_discussion_message_id = $4::BIGINT,
                    updated_at = NOW()
                WHERE channel_id = $1::BIGINT
                  AND message_id = $2::BIGINT
                  AND source_type = 'channel'
                """,
                int(linked_channel_id),
                int(linked_message_id),
                int(event.discussion_chat_id),
                int(event.message_id),
            )
        return int(linked_channel_id), int(linked_message_id)

    async def upsert_message(
        self,
        *,
        event: DiscussionMessageEvent,
        parent_channel_id: int,
        root_channel_id: int | None,
        root_message_id: int | None,
        hashtags: list[str],
        is_prompt: bool,
        links: list[str],
    ) -> None:
        root_is_channel_post = (
            root_channel_id is not None
            and root_message_id is not None
            and root_channel_id == parent_channel_id
        )
        async with self._database._require_pool().acquire() as connection:
            await connection.execute(
                """
                INSERT INTO channel_posts (
                    channel_id,
                    message_id,
                    media_group_id,
                    posted_at,
                    edited_at,
                    text_content,
                    media_type,
                    telegram_file_id,
                    telegram_file_unique_id,
                    file_size,
                    mime_type,
                    original_file_name,
                    has_spoiler,
                    hashtags,
                    hashtag_count,
                    is_prompt,
                    source_type,
                    parent_channel_id,
                    sender_id,
                    sender_name,
                    reply_to_message_id,
                    root_channel_id,
                    root_message_id,
                    root_is_channel_post,
                    is_automatic_forward,
                    linked_channel_message_id,
                    links,
                    updated_at
                )
                VALUES (
                    $1::BIGINT,
                    $2::BIGINT,
                    $3::TEXT,
                    $4::TIMESTAMPTZ,
                    $5::TIMESTAMPTZ,
                    $6::TEXT,
                    $7::VARCHAR,
                    $8::TEXT,
                    $9::TEXT,
                    $10::BIGINT,
                    $11::TEXT,
                    $12::TEXT,
                    $13::BOOLEAN,
                    $14::JSONB,
                    $15::INTEGER,
                    $16::BOOLEAN,
                    'discussion',
                    $17::BIGINT,
                    $18::TEXT,
                    $19::TEXT,
                    $20::BIGINT,
                    $21::BIGINT,
                    $22::BIGINT,
                    $23::BOOLEAN,
                    $24::BOOLEAN,
                    $25::BIGINT,
                    $26::JSONB,
                    NOW()
                )
                ON CONFLICT (channel_id, message_id) DO UPDATE
                SET media_group_id = EXCLUDED.media_group_id,
                    posted_at = EXCLUDED.posted_at,
                    edited_at = EXCLUDED.edited_at,
                    text_content = EXCLUDED.text_content,
                    media_type = EXCLUDED.media_type,
                    telegram_file_id = EXCLUDED.telegram_file_id,
                    telegram_file_unique_id = EXCLUDED.telegram_file_unique_id,
                    file_size = EXCLUDED.file_size,
                    mime_type = EXCLUDED.mime_type,
                    original_file_name = EXCLUDED.original_file_name,
                    has_spoiler = EXCLUDED.has_spoiler,
                    hashtags = EXCLUDED.hashtags,
                    hashtag_count = EXCLUDED.hashtag_count,
                    is_prompt = EXCLUDED.is_prompt,
                    source_type = 'discussion',
                    parent_channel_id = EXCLUDED.parent_channel_id,
                    sender_id = EXCLUDED.sender_id,
                    sender_name = EXCLUDED.sender_name,
                    reply_to_message_id = EXCLUDED.reply_to_message_id,
                    root_channel_id = EXCLUDED.root_channel_id,
                    root_message_id = EXCLUDED.root_message_id,
                    root_is_channel_post = EXCLUDED.root_is_channel_post,
                    is_automatic_forward = EXCLUDED.is_automatic_forward,
                    linked_channel_message_id = EXCLUDED.linked_channel_message_id,
                    links = EXCLUDED.links,
                    updated_at = NOW()
                """,
                int(event.discussion_chat_id),
                int(event.message_id),
                event.media_group_id,
                event.posted_at,
                event.edited_at,
                event.text_content,
                event.media_type,
                event.telegram_file_id,
                event.telegram_file_unique_id,
                event.file_size,
                event.mime_type,
                event.original_file_name,
                bool(event.has_spoiler),
                hashtags,
                len(hashtags),
                bool(is_prompt),
                int(parent_channel_id),
                event.sender_id,
                event.sender_name,
                event.reply_to_message_id,
                root_channel_id,
                root_message_id,
                bool(root_is_channel_post),
                bool(event.is_automatic_forward),
                event.forward_message_id,
                links,
            )


__all__ = ("DiscussionIngestRepository",)

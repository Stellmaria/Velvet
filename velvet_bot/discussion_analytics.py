from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from aiogram.types import Message

from velvet_bot.channel_analytics import (
    analyze_prompt_text,
    compact_identity,
    detect_media_type,
    extract_hashtags,
    extract_links,
)
from velvet_bot.database import Database
from velvet_bot.telegram_export_import import is_tracked_discussion


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


def _sender_name(message: Message) -> str | None:
    if message.from_user is not None:
        return message.from_user.full_name
    if message.sender_chat is not None:
        return message.sender_chat.title or message.sender_chat.username
    return None


def _sender_id(message: Message) -> str | None:
    if message.from_user is not None:
        return f"user{message.from_user.id}"
    if message.sender_chat is not None:
        return f"chat{message.sender_chat.id}"
    return None


async def ingest_live_discussion_message(
    database: Database,
    message: Message,
) -> bool:
    if not await is_tracked_discussion(database, message.chat.id):
        return False
    if message.from_user is not None and message.from_user.is_bot:
        return False

    text_content = message.text or message.caption or ""
    prompt = analyze_prompt_text(text_content)
    media_group_id = str(message.media_group_id) if message.media_group_id else None
    publication_key = (
        f"live-album:{media_group_id}"
        if media_group_id
        else f"live-message:{message.message_id}"
    )
    reply_to_message_id = (
        message.reply_to_message.message_id if message.reply_to_message else None
    )
    topic_id = getattr(message, "message_thread_id", None)
    sender_id = _sender_id(message)
    sender_name = _sender_name(message)
    media_type = detect_media_type(message)

    async with database._require_pool().acquire() as connection:
        character_rows = await connection.fetch(
            "SELECT id, normalized_name FROM characters"
        )
        character_by_alias = {
            compact_identity(str(row["normalized_name"])): int(row["id"])
            for row in character_rows
        }
        async with connection.transaction():
            await connection.execute(
                """
                UPDATE tracked_channels
                SET title = COALESCE($2, title),
                    username = COALESCE($3, username),
                    last_post_at = GREATEST(last_post_at, $4),
                    updated_at = NOW()
                WHERE chat_id = $1
                  AND source_kind = 'discussion'
                """,
                message.chat.id,
                message.chat.title,
                message.chat.username,
                message.date,
            )
            post_id = await connection.fetchval(
                """
                INSERT INTO channel_posts (
                    channel_id, message_id, publication_key, posted_at,
                    edited_at, author_signature, text_content, text_length,
                    media_type, media_group_id, has_spoiler,
                    is_prompt, prompt_score, has_important_section,
                    has_strict_section, has_negative_section,
                    has_technical_section, has_palette,
                    sender_id, sender_name, reply_to_message_id, topic_id,
                    reactions_total, reaction_breakdown,
                    imported_from_export, updated_at
                )
                VALUES (
                    $1, $2, $3, $4,
                    $5, $6, $7, $8,
                    $9, $10, $11,
                    $12, $13, $14,
                    $15, $16,
                    $17, $18,
                    $19, $20, $21, $22,
                    0, '{}'::JSONB,
                    FALSE, NOW()
                )
                ON CONFLICT (channel_id, message_id) DO UPDATE
                SET publication_key = EXCLUDED.publication_key,
                    edited_at = EXCLUDED.edited_at,
                    text_content = EXCLUDED.text_content,
                    text_length = EXCLUDED.text_length,
                    media_type = EXCLUDED.media_type,
                    media_group_id = EXCLUDED.media_group_id,
                    has_spoiler = EXCLUDED.has_spoiler,
                    is_prompt = EXCLUDED.is_prompt,
                    prompt_score = EXCLUDED.prompt_score,
                    has_important_section = EXCLUDED.has_important_section,
                    has_strict_section = EXCLUDED.has_strict_section,
                    has_negative_section = EXCLUDED.has_negative_section,
                    has_technical_section = EXCLUDED.has_technical_section,
                    has_palette = EXCLUDED.has_palette,
                    sender_id = EXCLUDED.sender_id,
                    sender_name = EXCLUDED.sender_name,
                    reply_to_message_id = EXCLUDED.reply_to_message_id,
                    topic_id = EXCLUDED.topic_id,
                    updated_at = NOW()
                RETURNING id
                """,
                message.chat.id,
                message.message_id,
                publication_key,
                message.date,
                message.edit_date,
                sender_name,
                text_content,
                len(text_content),
                media_type,
                media_group_id,
                bool(getattr(message, "has_media_spoiler", False)),
                prompt.is_prompt,
                prompt.score,
                prompt.has_important,
                prompt.has_strict,
                prompt.has_negative,
                prompt.has_technical,
                prompt.has_palette,
                sender_id,
                sender_name,
                reply_to_message_id,
                topic_id,
            )
            if post_id is None:
                return False

            await connection.execute(
                "DELETE FROM channel_post_hashtags WHERE post_id = $1",
                post_id,
            )
            await connection.execute(
                "DELETE FROM channel_post_links WHERE post_id = $1",
                post_id,
            )
            for display, normalized in extract_hashtags(text_content):
                character_id = character_by_alias.get(compact_identity(normalized))
                await connection.execute(
                    """
                    INSERT INTO channel_post_hashtags (
                        post_id, hashtag, normalized_hashtag,
                        character_id, is_character
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (post_id, normalized_hashtag) DO UPDATE
                    SET hashtag = EXCLUDED.hashtag,
                        character_id = EXCLUDED.character_id,
                        is_character = EXCLUDED.is_character
                    """,
                    post_id,
                    display,
                    normalized,
                    character_id,
                    character_id is not None,
                )
            for url, domain, is_telegram in extract_links(text_content):
                await connection.execute(
                    """
                    INSERT INTO channel_post_links (
                        post_id, url, domain, is_telegram
                    )
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (post_id, url) DO UPDATE
                    SET domain = EXCLUDED.domain,
                        is_telegram = EXCLUDED.is_telegram
                    """,
                    post_id,
                    url,
                    domain,
                    is_telegram,
                )
    return True


async def get_discussion_overview(
    database: Database,
    chat_id: int,
) -> DiscussionOverview:
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                COUNT(*) AS total_messages,
                COUNT(DISTINCT publication_key) AS total_publications,
                COUNT(DISTINCT sender_id) FILTER (WHERE sender_id IS NOT NULL)
                    AS unique_participants,
                COUNT(*) FILTER (WHERE reply_to_message_id IS NOT NULL)
                    AS reply_messages,
                COUNT(*) FILTER (WHERE media_type <> 'text') AS media_messages,
                COUNT(*) FILTER (WHERE has_spoiler) AS spoiler_messages,
                COUNT(*) FILTER (WHERE is_prompt) AS prompt_messages,
                COALESCE(SUM(reactions_total), 0) AS total_reactions,
                MIN(posted_at) AS first_message_at,
                MAX(posted_at) AS last_message_at
            FROM channel_posts
            WHERE channel_id = $1
            """,
            chat_id,
        )
        hashtag_row = await connection.fetchrow(
            """
            SELECT
                COUNT(*) AS total_hashtag_uses,
                COUNT(DISTINCT h.normalized_hashtag) AS unique_hashtags
            FROM channel_post_hashtags AS h
            JOIN channel_posts AS p ON p.id = h.post_id
            WHERE p.channel_id = $1
            """,
            chat_id,
        )
    return DiscussionOverview(
        chat_id=chat_id,
        total_messages=int(row["total_messages"] or 0),
        total_publications=int(row["total_publications"] or 0),
        unique_participants=int(row["unique_participants"] or 0),
        reply_messages=int(row["reply_messages"] or 0),
        media_messages=int(row["media_messages"] or 0),
        spoiler_messages=int(row["spoiler_messages"] or 0),
        prompt_messages=int(row["prompt_messages"] or 0),
        total_hashtag_uses=int(hashtag_row["total_hashtag_uses"] or 0),
        unique_hashtags=int(hashtag_row["unique_hashtags"] or 0),
        total_reactions=int(row["total_reactions"] or 0),
        first_message_at=row["first_message_at"],
        last_message_at=row["last_message_at"],
    )


async def list_participant_stats(
    database: Database,
    chat_id: int,
    *,
    limit: int = 20,
) -> list[ParticipantStat]:
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                COALESCE(sender_id, 'unknown') AS sender_id,
                COALESCE(MAX(sender_name), 'Неизвестный участник') AS sender_name,
                COUNT(*) AS message_count,
                COUNT(*) FILTER (WHERE reply_to_message_id IS NOT NULL)
                    AS reply_count,
                COUNT(*) FILTER (WHERE media_type <> 'text') AS media_count,
                COUNT(h.normalized_hashtag) AS hashtag_count,
                MAX(p.posted_at) AS last_message_at
            FROM channel_posts AS p
            LEFT JOIN channel_post_hashtags AS h ON h.post_id = p.id
            WHERE p.channel_id = $1
            GROUP BY COALESCE(sender_id, 'unknown')
            ORDER BY message_count DESC, last_message_at DESC
            LIMIT $2
            """,
            chat_id,
            max(1, min(limit, 100)),
        )
    return [
        ParticipantStat(
            sender_id=str(row["sender_id"]),
            sender_name=str(row["sender_name"]),
            message_count=int(row["message_count"] or 0),
            reply_count=int(row["reply_count"] or 0),
            media_count=int(row["media_count"] or 0),
            hashtag_count=int(row["hashtag_count"] or 0),
            last_message_at=row["last_message_at"],
        )
        for row in rows
    ]

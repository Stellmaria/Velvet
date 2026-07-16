from __future__ import annotations

from datetime import datetime

from velvet_bot.channel_analytics import compact_identity
from velvet_bot.database import Database
from velvet_bot.domains.discussions.models import DiscussionMessageEvent


class DiscussionIngestRepository:
    """PostgreSQL boundary for live discussion message ingestion."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def get_parent_channel_id(self, chat_id: int) -> int | None:
        async with self._database._require_pool().acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT parent_channel_id
                FROM tracked_channels
                WHERE chat_id = $1::BIGINT
                  AND source_kind = 'discussion'
                  AND enabled = TRUE
                """,
                int(chat_id),
            )
        return int(value) if value is not None else None

    async def resolve_root_message_id(
        self,
        event: DiscussionMessageEvent,
        *,
        is_root: bool,
    ) -> int | None:
        if is_root:
            return int(event.message_id)
        if event.reply_to_message_id is None:
            return None
        async with self._database._require_pool().acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT message_id, discussion_root_message_id, is_discussion_root
                FROM channel_posts
                WHERE channel_id = $1::BIGINT
                  AND message_id = $2::BIGINT
                """,
                int(event.chat_id),
                int(event.reply_to_message_id),
            )
        if row is not None:
            if row["discussion_root_message_id"] is not None:
                return int(row["discussion_root_message_id"])
            if bool(row["is_discussion_root"]):
                return int(row["message_id"])
        if event.reply_is_automatic_forward:
            return int(event.reply_to_message_id)
        return None

    async def store_message(
        self,
        event: DiscussionMessageEvent,
        *,
        parent_channel_id: int,
        source_channel_message_id: int | None,
        root_message_id: int | None,
        is_root: bool,
        publication_key: str,
        is_prompt: bool,
        prompt_score: int,
        has_important: bool,
        has_strict: bool,
        has_negative: bool,
        has_technical: bool,
        has_palette: bool,
        hashtags: tuple[tuple[str, str], ...],
        links: tuple[tuple[str, str, bool], ...],
    ) -> bool:
        async with self._database._require_pool().acquire() as connection:
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
                    SET title = COALESCE($2::TEXT, title),
                        username = COALESCE($3::TEXT, username),
                        last_post_at = GREATEST(last_post_at, $4::TIMESTAMPTZ),
                        updated_at = NOW()
                    WHERE chat_id = $1::BIGINT
                      AND source_kind = 'discussion'
                    """,
                    int(event.chat_id),
                    event.chat_title,
                    event.chat_username,
                    event.posted_at,
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
                        imported_from_export, discussion_root_message_id,
                        is_discussion_root, source_channel_message_id, updated_at
                    )
                    VALUES (
                        $1::BIGINT, $2::BIGINT, $3::TEXT, $4::TIMESTAMPTZ,
                        $5::TIMESTAMPTZ, $6::TEXT, $7::TEXT, $8::INTEGER,
                        $9::VARCHAR, $10::TEXT, $11::BOOLEAN,
                        $12::BOOLEAN, $13::INTEGER, $14::BOOLEAN,
                        $15::BOOLEAN, $16::BOOLEAN,
                        $17::BOOLEAN, $18::BOOLEAN,
                        $19::TEXT, $20::TEXT, $21::BIGINT, $22::BIGINT,
                        0, '{}'::JSONB,
                        FALSE, $23::BIGINT, $24::BOOLEAN, $25::BIGINT, NOW()
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
                        discussion_root_message_id = COALESCE(
                            EXCLUDED.discussion_root_message_id,
                            channel_posts.discussion_root_message_id
                        ),
                        is_discussion_root = (
                            channel_posts.is_discussion_root
                            OR EXCLUDED.is_discussion_root
                        ),
                        source_channel_message_id = COALESCE(
                            EXCLUDED.source_channel_message_id,
                            channel_posts.source_channel_message_id
                        ),
                        updated_at = NOW()
                    RETURNING id
                    """,
                    int(event.chat_id),
                    int(event.message_id),
                    publication_key,
                    event.posted_at,
                    event.edited_at,
                    event.sender_name,
                    event.text_content,
                    len(event.text_content),
                    event.media_type,
                    event.media_group_id,
                    bool(event.has_spoiler),
                    bool(is_prompt),
                    int(prompt_score),
                    bool(has_important),
                    bool(has_strict),
                    bool(has_negative),
                    bool(has_technical),
                    bool(has_palette),
                    event.sender_id,
                    event.sender_name,
                    event.reply_to_message_id,
                    event.topic_id,
                    root_message_id,
                    bool(is_root),
                    source_channel_message_id,
                )
                if post_id is None:
                    return False

                await connection.execute(
                    "DELETE FROM channel_post_hashtags WHERE post_id = $1::BIGINT",
                    int(post_id),
                )
                await connection.execute(
                    "DELETE FROM channel_post_links WHERE post_id = $1::BIGINT",
                    int(post_id),
                )
                for display, normalized in hashtags:
                    character_id = character_by_alias.get(compact_identity(normalized))
                    await connection.execute(
                        """
                        INSERT INTO channel_post_hashtags (
                            post_id, hashtag, normalized_hashtag,
                            character_id, is_character
                        )
                        VALUES ($1::BIGINT, $2::TEXT, $3::TEXT, $4::BIGINT, $5::BOOLEAN)
                        ON CONFLICT (post_id, normalized_hashtag) DO UPDATE
                        SET hashtag = EXCLUDED.hashtag,
                            character_id = EXCLUDED.character_id,
                            is_character = EXCLUDED.is_character
                        """,
                        int(post_id),
                        display,
                        normalized,
                        character_id,
                        character_id is not None,
                    )
                for url, domain, is_telegram in links:
                    await connection.execute(
                        """
                        INSERT INTO channel_post_links (
                            post_id, url, domain, is_telegram
                        )
                        VALUES ($1::BIGINT, $2::TEXT, $3::TEXT, $4::BOOLEAN)
                        ON CONFLICT (post_id, url) DO UPDATE
                        SET domain = EXCLUDED.domain,
                            is_telegram = EXCLUDED.is_telegram
                        """,
                        int(post_id),
                        url,
                        domain,
                        bool(is_telegram),
                    )

                if root_message_id is not None:
                    root_text = event.text_content
                    root_date = event.posted_at
                    resolved_source_id = source_channel_message_id
                    if not is_root and event.reply_to_message_id is not None:
                        root_row = await connection.fetchrow(
                            """
                            SELECT text_content, posted_at, source_channel_message_id
                            FROM channel_posts
                            WHERE channel_id = $1::BIGINT
                              AND message_id = $2::BIGINT
                            """,
                            int(event.chat_id),
                            int(root_message_id),
                        )
                        if root_row is not None:
                            root_text = str(root_row["text_content"] or "")
                            root_date = root_row["posted_at"]
                            if resolved_source_id is None:
                                resolved_source_id = root_row[
                                    "source_channel_message_id"
                                ]
                        elif event.reply_date is not None:
                            root_text = event.reply_text
                            root_date = event.reply_date
                    await self._upsert_thread(
                        connection,
                        discussion_chat_id=event.chat_id,
                        root_message_id=root_message_id,
                        parent_channel_id=parent_channel_id,
                        source_channel_message_id=(
                            int(resolved_source_id)
                            if resolved_source_id is not None
                            else None
                        ),
                        root_text=root_text,
                        root_date=root_date,
                    )
        return True

    @staticmethod
    async def _match_channel_post(
        connection,
        *,
        parent_channel_id: int,
        source_channel_message_id: int | None,
        root_text: str,
        root_date: datetime,
    ) -> tuple[int | None, int | None, str]:
        if source_channel_message_id is not None:
            row = await connection.fetchrow(
                """
                SELECT id, message_id
                FROM channel_posts
                WHERE channel_id = $1::BIGINT
                  AND message_id = $2::BIGINT
                """,
                int(parent_channel_id),
                int(source_channel_message_id),
            )
            return (
                int(row["id"]) if row else None,
                int(source_channel_message_id),
                "live_forward" if row else "pending_forward",
            )
        if root_text.strip():
            row = await connection.fetchrow(
                """
                SELECT id, message_id
                FROM channel_posts
                WHERE channel_id = $1::BIGINT
                  AND text_content = $2::TEXT
                  AND ABS(EXTRACT(EPOCH FROM (posted_at - $3::TIMESTAMPTZ))) <= 3600
                ORDER BY ABS(EXTRACT(EPOCH FROM (posted_at - $3::TIMESTAMPTZ))), id
                LIMIT 1
                """,
                int(parent_channel_id),
                root_text,
                root_date,
            )
            if row is not None:
                return int(row["id"]), int(row["message_id"]), "live_exact_text"
        return None, None, "pending"

    async def _upsert_thread(
        self,
        connection,
        *,
        discussion_chat_id: int,
        root_message_id: int,
        parent_channel_id: int,
        source_channel_message_id: int | None,
        root_text: str,
        root_date: datetime,
    ) -> None:
        channel_post_id, channel_message_id, link_source = (
            await self._match_channel_post(
                connection,
                parent_channel_id=parent_channel_id,
                source_channel_message_id=source_channel_message_id,
                root_text=root_text,
                root_date=root_date,
            )
        )
        await connection.execute(
            """
            INSERT INTO discussion_threads (
                discussion_chat_id, root_message_id, parent_channel_id,
                channel_message_id, channel_post_id, link_source, updated_at
            )
            VALUES (
                $1::BIGINT, $2::BIGINT, $3::BIGINT,
                $4::BIGINT, $5::BIGINT, $6::VARCHAR, NOW()
            )
            ON CONFLICT (discussion_chat_id, root_message_id) DO UPDATE
            SET parent_channel_id = EXCLUDED.parent_channel_id,
                channel_message_id = COALESCE(
                    discussion_threads.channel_message_id,
                    EXCLUDED.channel_message_id
                ),
                channel_post_id = COALESCE(
                    discussion_threads.channel_post_id,
                    EXCLUDED.channel_post_id
                ),
                link_source = CASE
                    WHEN discussion_threads.channel_post_id IS NULL
                        THEN EXCLUDED.link_source
                    ELSE discussion_threads.link_source
                END,
                updated_at = NOW()
            """,
            int(discussion_chat_id),
            int(root_message_id),
            int(parent_channel_id),
            channel_message_id,
            channel_post_id,
            link_source,
        )


__all__ = ("DiscussionIngestRepository",)

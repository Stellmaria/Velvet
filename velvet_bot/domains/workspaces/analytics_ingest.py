from __future__ import annotations

from aiogram.types import Message

from velvet_bot.channel_analytics import ParsedChannelPost, compact_identity, parse_channel_post
from velvet_bot.database import Database


async def ingest_workspace_channel_post(
    database: Database,
    message: Message,
    *,
    workspace_id: int,
) -> ParsedChannelPost:
    """Store a channel post while resolving hashtags only inside one workspace."""
    parsed = parse_channel_post(message)
    async with database.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                """
                INSERT INTO tracked_channels (
                    chat_id, title, username, enabled, last_post_at, updated_at
                )
                VALUES ($1, $2, $3, TRUE, $4, NOW())
                ON CONFLICT (chat_id) DO UPDATE
                SET title = EXCLUDED.title,
                    username = EXCLUDED.username,
                    enabled = TRUE,
                    last_post_at = GREATEST(
                        tracked_channels.last_post_at,
                        EXCLUDED.last_post_at
                    ),
                    updated_at = NOW()
                """,
                parsed.channel_id,
                parsed.title,
                parsed.username,
                parsed.posted_at,
            )
            post_id = await connection.fetchval(
                """
                INSERT INTO channel_posts (
                    channel_id, message_id, publication_key, posted_at, edited_at,
                    author_signature, text_content, text_length, media_type,
                    media_group_id, has_spoiler, view_count, forward_count,
                    is_prompt, prompt_score, has_important_section,
                    has_strict_section, has_negative_section,
                    has_technical_section, has_palette, message_url, updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8, $9,
                    $10, $11, $12, $13,
                    $14, $15, $16,
                    $17, $18,
                    $19, $20, $21, NOW()
                )
                ON CONFLICT (channel_id, message_id) DO UPDATE
                SET publication_key = EXCLUDED.publication_key,
                    posted_at = EXCLUDED.posted_at,
                    edited_at = EXCLUDED.edited_at,
                    author_signature = EXCLUDED.author_signature,
                    text_content = EXCLUDED.text_content,
                    text_length = EXCLUDED.text_length,
                    media_type = EXCLUDED.media_type,
                    media_group_id = EXCLUDED.media_group_id,
                    has_spoiler = EXCLUDED.has_spoiler,
                    view_count = EXCLUDED.view_count,
                    forward_count = EXCLUDED.forward_count,
                    is_prompt = EXCLUDED.is_prompt,
                    prompt_score = EXCLUDED.prompt_score,
                    has_important_section = EXCLUDED.has_important_section,
                    has_strict_section = EXCLUDED.has_strict_section,
                    has_negative_section = EXCLUDED.has_negative_section,
                    has_technical_section = EXCLUDED.has_technical_section,
                    has_palette = EXCLUDED.has_palette,
                    message_url = EXCLUDED.message_url,
                    updated_at = NOW()
                RETURNING id
                """,
                parsed.channel_id,
                parsed.message_id,
                parsed.publication_key,
                parsed.posted_at,
                parsed.edited_at,
                parsed.author_signature,
                parsed.text_content,
                len(parsed.text_content),
                parsed.media_type,
                parsed.media_group_id,
                parsed.has_spoiler,
                parsed.view_count,
                parsed.forward_count,
                parsed.prompt.is_prompt,
                parsed.prompt.score,
                parsed.prompt.has_important,
                parsed.prompt.has_strict,
                parsed.prompt.has_negative,
                parsed.prompt.has_technical,
                parsed.prompt.has_palette,
                parsed.message_url,
            )
            if post_id is None:
                raise RuntimeError("Не удалось сохранить пост канала пространства.")

            await connection.execute(
                "DELETE FROM channel_post_hashtags WHERE post_id = $1",
                post_id,
            )
            await connection.execute(
                "DELETE FROM channel_post_links WHERE post_id = $1",
                post_id,
            )

            alias_rows = await connection.fetch(
                """
                SELECT c.id, c.name, alias.normalized_alias
                FROM workspace_character_aliases AS alias
                JOIN characters AS c
                  ON c.workspace_id = alias.workspace_id
                 AND c.id = alias.character_id
                WHERE alias.workspace_id = $1::BIGINT
                """,
                int(workspace_id),
            )
            character_by_alias = {
                compact_identity(str(row["normalized_alias"])): (
                    int(row["id"]),
                    str(row["name"]),
                )
                for row in alias_rows
            }
            for display, normalized in parsed.hashtags:
                character = character_by_alias.get(compact_identity(normalized))
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
                    character[0] if character else None,
                    character is not None,
                )

            for url, domain, is_telegram in parsed.links:
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
    return parsed


__all__ = ("ingest_workspace_channel_post",)

from __future__ import annotations

from velvet_bot import analytics_review as review_module
from velvet_bot.analytics_dashboard import normalize_period, period_since
from velvet_bot.database import Database


async def list_publication_reviews(
    database: Database,
    channel_id: int,
    *,
    period: str,
    page: int,
    page_size: int = 6,
    low_confidence_only: bool = True,
) -> review_module.ReviewPage:
    """Load representative publications with PostgreSQL-valid DISTINCT ordering."""
    since = period_since(normalize_period(period))
    safe_size = max(1, min(page_size, 8))
    safe_page = max(0, page)
    review_filter = (
        "AND post_type_source = 'automatic' "
        "AND (post_type_confidence < 75 OR post_type = 'unknown')"
        if low_confidence_only
        else ""
    )
    async with database.acquire() as connection:
        total = int(
            await connection.fetchval(
                f"""
                SELECT COUNT(DISTINCT publication_key)
                FROM channel_posts
                WHERE channel_id = $1
                  AND ($2::TIMESTAMPTZ IS NULL OR posted_at >= $2)
                  {review_filter}
                """,
                channel_id,
                since,
            )
            or 0
        )
        total_pages = max(1, (total + safe_size - 1) // safe_size)
        normalized_page = min(safe_page, total_pages - 1)
        rows = await connection.fetch(
            f"""
            WITH representatives AS (
                SELECT DISTINCT ON (publication_key)
                    publication_key,
                    message_id,
                    posted_at,
                    text_content,
                    media_type,
                    message_url,
                    post_type,
                    post_type_confidence,
                    post_type_source,
                    is_prompt,
                    text_length,
                    id
                FROM channel_posts
                WHERE channel_id = $1
                  AND ($2::TIMESTAMPTZ IS NULL OR posted_at >= $2)
                  {review_filter}
                ORDER BY publication_key, text_length DESC, id
            ), counts AS (
                SELECT publication_key, COUNT(*) AS media_count
                FROM channel_posts
                WHERE channel_id = $1
                GROUP BY publication_key
            )
            SELECT r.*, c.media_count
            FROM representatives AS r
            JOIN counts AS c USING (publication_key)
            ORDER BY r.posted_at DESC, r.message_id DESC
            OFFSET $3
            LIMIT $4
            """,
            channel_id,
            since,
            normalized_page * safe_size,
            safe_size,
        )
        items: list[review_module.PublicationReview] = []
        for row in rows:
            publication_key = str(row["publication_key"])
            token_id = await review_module._ensure_review_token(
                connection,
                channel_id=channel_id,
                item_kind="publication",
                item_key=publication_key,
            )
            items.append(
                review_module.PublicationReview(
                    token_id=token_id,
                    publication_key=publication_key,
                    message_id=int(row["message_id"]),
                    posted_at=row["posted_at"],
                    text_content=str(row["text_content"] or ""),
                    media_type=str(row["media_type"]),
                    media_count=int(row["media_count"] or 0),
                    message_url=row["message_url"],
                    post_type=str(row["post_type"]),
                    confidence=int(row["post_type_confidence"] or 0),
                    source=str(row["post_type_source"]),
                    is_prompt=bool(row["is_prompt"]),
                )
            )
    return review_module.ReviewPage(items, normalized_page, safe_size, total)


def install() -> None:
    """Install the corrected query before analytics controllers import it."""
    review_module.list_publication_reviews = list_publication_reviews


__all__ = ("install", "list_publication_reviews")

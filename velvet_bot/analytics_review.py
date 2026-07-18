from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from velvet_bot.analytics_dashboard import normalize_period, period_since
from velvet_bot.character_aliases import add_character_alias
from velvet_bot.database import Database
from velvet_bot.post_classification import POST_TYPE_LABELS, classify_post


@dataclass(frozen=True, slots=True)
class ReviewPage:
    items: list[object]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)


@dataclass(frozen=True, slots=True)
class UnresolvedTagReview:
    token_id: int
    normalized_hashtag: str
    hashtag: str
    publication_count: int
    prompt_count: int
    character_id: int | None = None
    character_name: str | None = None


@dataclass(frozen=True, slots=True)
class CharacterPickerItem:
    id: int
    name: str
    category: str | None
    universe: str | None
    story_short_label: str | None


@dataclass(frozen=True, slots=True)
class PublicationReview:
    token_id: int
    publication_key: str
    message_id: int
    posted_at: datetime
    text_content: str
    media_type: str
    media_count: int
    message_url: str | None
    post_type: str
    confidence: int
    source: str
    is_prompt: bool
    hashtags: tuple[tuple[str, str], ...] = ()


async def _ensure_review_token(
    connection,
    *,
    channel_id: int,
    item_kind: str,
    item_key: str,
) -> int:
    token_id = await connection.fetchval(
        """
        INSERT INTO analytics_review_items (
            channel_id, item_kind, item_key, updated_at
        )
        VALUES ($1, $2, $3, NOW())
        ON CONFLICT (channel_id, item_kind, item_key) DO UPDATE
        SET updated_at = NOW()
        RETURNING id
        """,
        channel_id,
        item_kind,
        item_key,
    )
    if token_id is None:
        raise RuntimeError("Не удалось создать ключ проверки аналитики.")
    return int(token_id)


async def list_unresolved_tag_reviews(
    database: Database,
    channel_id: int,
    *,
    period: str,
    page: int,
    page_size: int = 6,
) -> ReviewPage:
    since = period_since(normalize_period(period))
    safe_size = max(1, min(page_size, 8))
    safe_page = max(0, page)
    async with database.acquire() as connection:
        total = int(
            await connection.fetchval(
                """
                SELECT COUNT(DISTINCT h.normalized_hashtag)
                FROM channel_post_hashtags AS h
                JOIN channel_posts AS p ON p.id = h.post_id
                WHERE p.channel_id = $1
                  AND h.character_id IS NULL
                  AND ($2::TIMESTAMPTZ IS NULL OR p.posted_at >= $2)
                """,
                channel_id,
                since,
            )
            or 0
        )
        total_pages = max(1, (total + safe_size - 1) // safe_size)
        normalized_page = min(safe_page, total_pages - 1)
        rows = await connection.fetch(
            """
            SELECT
                h.normalized_hashtag,
                MAX(h.hashtag) AS hashtag,
                COUNT(DISTINCT p.publication_key) AS publication_count,
                COUNT(DISTINCT p.publication_key) FILTER (WHERE p.is_prompt)
                    AS prompt_count
            FROM channel_post_hashtags AS h
            JOIN channel_posts AS p ON p.id = h.post_id
            WHERE p.channel_id = $1
              AND h.character_id IS NULL
              AND ($2::TIMESTAMPTZ IS NULL OR p.posted_at >= $2)
            GROUP BY h.normalized_hashtag
            ORDER BY publication_count DESC, h.normalized_hashtag
            OFFSET $3
            LIMIT $4
            """,
            channel_id,
            since,
            normalized_page * safe_size,
            safe_size,
        )
        items: list[UnresolvedTagReview] = []
        for row in rows:
            normalized_hashtag = str(row["normalized_hashtag"])
            token_id = await _ensure_review_token(
                connection,
                channel_id=channel_id,
                item_kind="hashtag",
                item_key=normalized_hashtag,
            )
            items.append(
                UnresolvedTagReview(
                    token_id=token_id,
                    normalized_hashtag=normalized_hashtag,
                    hashtag=str(row["hashtag"]),
                    publication_count=int(row["publication_count"] or 0),
                    prompt_count=int(row["prompt_count"] or 0),
                )
            )
    return ReviewPage(items, normalized_page, safe_size, total)


async def get_unresolved_tag_review(
    database: Database,
    *,
    token_id: int,
) -> UnresolvedTagReview | None:
    async with database.acquire() as connection:
        token = await connection.fetchrow(
            """
            SELECT channel_id, item_key
            FROM analytics_review_items
            WHERE id = $1 AND item_kind = 'hashtag'
            """,
            token_id,
        )
        if token is None:
            return None
        row = await connection.fetchrow(
            """
            SELECT
                MAX(h.hashtag) AS hashtag,
                COUNT(DISTINCT p.publication_key) AS publication_count,
                COUNT(DISTINCT p.publication_key) FILTER (WHERE p.is_prompt)
                    AS prompt_count,
                MAX(h.character_id) AS character_id,
                MAX(c.name) AS character_name
            FROM channel_post_hashtags AS h
            JOIN channel_posts AS p ON p.id = h.post_id
            LEFT JOIN characters AS c ON c.id = h.character_id
            WHERE p.channel_id = $1
              AND h.normalized_hashtag = $2
            """,
            int(token["channel_id"]),
            str(token["item_key"]),
        )
        if row is None or row["hashtag"] is None:
            return None
    return UnresolvedTagReview(
        token_id=token_id,
        normalized_hashtag=str(token["item_key"]),
        hashtag=str(row["hashtag"]),
        publication_count=int(row["publication_count"] or 0),
        prompt_count=int(row["prompt_count"] or 0),
        character_id=int(row["character_id"]) if row["character_id"] is not None else None,
        character_name=row["character_name"],
    )


async def list_character_picker(
    database: Database,
    *,
    page: int,
    page_size: int = 8,
) -> ReviewPage:
    safe_size = max(1, min(page_size, 10))
    safe_page = max(0, page)
    async with database.acquire() as connection:
        total = int(await connection.fetchval("SELECT COUNT(*) FROM characters") or 0)
        total_pages = max(1, (total + safe_size - 1) // safe_size)
        normalized_page = min(safe_page, total_pages - 1)
        rows = await connection.fetch(
            """
            SELECT
                c.id,
                c.name,
                c.category,
                c.universe,
                s.short_label AS story_short_label
            FROM characters AS c
            LEFT JOIN character_stories AS s ON s.id = c.story_id
            ORDER BY LOWER(c.name), c.id
            OFFSET $1
            LIMIT $2
            """,
            normalized_page * safe_size,
            safe_size,
        )
    return ReviewPage(
        [
            CharacterPickerItem(
                id=int(row["id"]),
                name=str(row["name"]),
                category=row["category"],
                universe=row["universe"],
                story_short_label=row["story_short_label"],
            )
            for row in rows
        ],
        normalized_page,
        safe_size,
        total,
    )


async def assign_unresolved_tag(
    database: Database,
    *,
    token_id: int,
    character_id: int,
    changed_by: int | None,
):
    item = await get_unresolved_tag_review(database, token_id=token_id)
    if item is None:
        raise ValueError("Хэштег больше не найден.")
    return await add_character_alias(
        database,
        character_id=character_id,
        alias=item.hashtag,
        created_by=changed_by,
    )


async def list_publication_reviews(
    database: Database,
    channel_id: int,
    *,
    period: str,
    page: int,
    page_size: int = 6,
    low_confidence_only: bool = True,
) -> ReviewPage:
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
                    is_prompt
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
        items: list[PublicationReview] = []
        for row in rows:
            publication_key = str(row["publication_key"])
            token_id = await _ensure_review_token(
                connection,
                channel_id=channel_id,
                item_kind="publication",
                item_key=publication_key,
            )
            items.append(
                PublicationReview(
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
    return ReviewPage(items, normalized_page, safe_size, total)


async def get_publication_review(
    database: Database,
    *,
    token_id: int,
) -> PublicationReview | None:
    async with database.acquire() as connection:
        token = await connection.fetchrow(
            """
            SELECT channel_id, item_key
            FROM analytics_review_items
            WHERE id = $1 AND item_kind = 'publication'
            """,
            token_id,
        )
        if token is None:
            return None
        channel_id = int(token["channel_id"])
        publication_key = str(token["item_key"])
        row = await connection.fetchrow(
            """
            SELECT
                message_id,
                posted_at,
                text_content,
                media_type,
                message_url,
                post_type,
                post_type_confidence,
                post_type_source,
                is_prompt
            FROM channel_posts
            WHERE channel_id = $1 AND publication_key = $2
            ORDER BY text_length DESC, id
            LIMIT 1
            """,
            channel_id,
            publication_key,
        )
        if row is None:
            return None
        media_count = int(
            await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM channel_posts
                WHERE channel_id = $1 AND publication_key = $2
                """,
                channel_id,
                publication_key,
            )
            or 0
        )
        hashtag_rows = await connection.fetch(
            """
            SELECT DISTINCT h.hashtag, h.normalized_hashtag
            FROM channel_post_hashtags AS h
            JOIN channel_posts AS p ON p.id = h.post_id
            WHERE p.channel_id = $1 AND p.publication_key = $2
            ORDER BY h.normalized_hashtag
            """,
            channel_id,
            publication_key,
        )
    return PublicationReview(
        token_id=token_id,
        publication_key=publication_key,
        message_id=int(row["message_id"]),
        posted_at=row["posted_at"],
        text_content=str(row["text_content"] or ""),
        media_type=str(row["media_type"]),
        media_count=media_count,
        message_url=row["message_url"],
        post_type=str(row["post_type"]),
        confidence=int(row["post_type_confidence"] or 0),
        source=str(row["post_type_source"]),
        is_prompt=bool(row["is_prompt"]),
        hashtags=tuple(
            (str(item["hashtag"]), str(item["normalized_hashtag"]))
            for item in hashtag_rows
        ),
    )


async def _record_classification_change(
    connection,
    *,
    channel_id: int,
    publication_key: str,
    previous_type: str,
    new_type: str,
    previous_confidence: int,
    new_confidence: int,
    previous_source: str,
    new_source: str,
    changed_by: int | None,
    reason: str,
) -> None:
    await connection.execute(
        """
        INSERT INTO post_classification_changes (
            channel_id, publication_key,
            previous_type, new_type,
            previous_confidence, new_confidence,
            previous_source, new_source,
            changed_by, reason
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """,
        channel_id,
        publication_key,
        previous_type,
        new_type,
        previous_confidence,
        new_confidence,
        previous_source,
        new_source,
        changed_by,
        reason,
    )


async def set_manual_publication_type(
    database: Database,
    *,
    token_id: int,
    post_type: str,
    changed_by: int | None,
) -> PublicationReview:
    if post_type not in POST_TYPE_LABELS:
        raise ValueError("Неизвестный тип публикации.")
    item = await get_publication_review(database, token_id=token_id)
    if item is None:
        raise ValueError("Публикация больше не найдена.")

    async with database.acquire() as connection:
        async with connection.transaction():
            channel_id = int(
                await connection.fetchval(
                    """
                    SELECT channel_id
                    FROM analytics_review_items
                    WHERE id = $1::BIGINT
                    """,
                    token_id,
                )
            )
            await _record_classification_change(
                connection,
                channel_id=channel_id,
                publication_key=item.publication_key,
                previous_type=item.post_type,
                new_type=post_type,
                previous_confidence=item.confidence,
                new_confidence=100,
                previous_source=item.source,
                new_source="manual",
                changed_by=changed_by,
                reason="ручной выбор в аналитическом центре",
            )
            await connection.execute(
                """
                UPDATE channel_posts
                SET post_type = $3::VARCHAR,
                    post_type_confidence = 100,
                    post_type_source = 'manual',
                    is_prompt = ($3::VARCHAR = 'prompt'::VARCHAR),
                    updated_at = NOW()
                WHERE channel_id = $1::BIGINT
                  AND publication_key = $2::VARCHAR
                """,
                channel_id,
                item.publication_key,
                post_type,
            )

    refreshed = await get_publication_review(database, token_id=token_id)
    if refreshed is None:
        raise RuntimeError("Публикация исчезла после обновления.")
    return refreshed


async def reset_publication_type_to_automatic(
    database: Database,
    *,
    token_id: int,
    changed_by: int | None,
) -> PublicationReview:
    item = await get_publication_review(database, token_id=token_id)
    if item is None:
        raise ValueError("Публикация больше не найдена.")
    classification = classify_post(
        item.text_content,
        item.hashtags,
        is_prompt=item.is_prompt,
        media_type=item.media_type,
    )
    async with database.acquire() as connection:
        channel_id = int(
            await connection.fetchval(
                "SELECT channel_id FROM analytics_review_items WHERE id = $1",
                token_id,
            )
        )
        async with connection.transaction():
            await _record_classification_change(
                connection,
                channel_id=channel_id,
                publication_key=item.publication_key,
                previous_type=item.post_type,
                new_type=classification.post_type,
                previous_confidence=item.confidence,
                new_confidence=classification.confidence,
                previous_source=item.source,
                new_source="automatic",
                changed_by=changed_by,
                reason=f"возврат автоматической классификации: {classification.reason}",
            )
            await connection.execute(
                """
                UPDATE channel_posts
                SET post_type_source = 'automatic',
                    is_prompt = $3,
                    updated_at = NOW()
                WHERE channel_id = $1 AND publication_key = $2
                """,
                channel_id,
                item.publication_key,
                classification.post_type == "prompt",
            )
            await connection.execute(
                """
                UPDATE channel_posts
                SET post_type = $3,
                    post_type_confidence = $4,
                    post_type_source = 'automatic',
                    updated_at = NOW()
                WHERE channel_id = $1 AND publication_key = $2
                """,
                channel_id,
                item.publication_key,
                classification.post_type,
                classification.confidence,
            )
    refreshed = await get_publication_review(database, token_id=token_id)
    if refreshed is None:
        raise RuntimeError("Публикация исчезла после обновления.")
    return refreshed


async def reclassify_automatic_publications(
    database: Database,
    *,
    channel_id: int,
    changed_by: int | None,
) -> tuple[int, int]:
    async with database.acquire() as connection:
        keys = await connection.fetch(
            """
            SELECT DISTINCT publication_key
            FROM channel_posts
            WHERE channel_id = $1 AND post_type_source = 'automatic'
            ORDER BY publication_key
            """,
            channel_id,
        )
    changed = 0
    for key_row in keys:
        publication_key = str(key_row["publication_key"])
        async with database.acquire() as connection:
            token_id = await _ensure_review_token(
                connection,
                channel_id=channel_id,
                item_kind="publication",
                item_key=publication_key,
            )
        before = await get_publication_review(database, token_id=token_id)
        after = await reset_publication_type_to_automatic(
            database,
            token_id=token_id,
            changed_by=changed_by,
        )
        if before and (
            before.post_type != after.post_type
            or before.confidence != after.confidence
        ):
            changed += 1
    return changed, len(keys)

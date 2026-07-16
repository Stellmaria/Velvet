from __future__ import annotations

import json

from velvet_bot.database import Database
from velvet_bot.domains.publication.models import (
    DuplicateDraftInfo,
    DuplicatePostInfo,
    PublicationCharacterInfo,
    PublicationDraft,
    PublicationIssue,
    PublicationValidationContext,
)
from velvet_bot.domains.publication.repository import PublicationRepository


class PublicationValidationRepository:
    """Read and persist data required by publication content validation."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._drafts = PublicationRepository(database)

    async def load_context(
        self,
        draft: PublicationDraft,
        *,
        normalized_aliases: list[str],
        text: str,
    ) -> PublicationValidationContext:
        async with self._database._require_pool().acquire() as connection:
            character_rows = []
            if normalized_aliases:
                character_rows = await connection.fetch(
                    """
                    SELECT DISTINCT
                        c.id, c.name, c.category, c.universe, c.story_id,
                        EXISTS (
                            SELECT 1
                            FROM character_story_links AS csl
                            WHERE csl.character_id = c.id
                        ) AS has_multi_story,
                        a.normalized_alias
                    FROM character_aliases AS a
                    JOIN characters AS c ON c.id = a.character_id
                    WHERE a.normalized_alias = ANY($1::TEXT[])
                    """,
                    normalized_aliases,
                )

            duplicate_draft_row = await connection.fetchrow(
                """
                SELECT id, status
                FROM publication_drafts
                WHERE target_chat_id = $1::BIGINT
                  AND content_hash = $2::CHAR(64)
                  AND id <> $3::BIGINT
                  AND status IN ('scheduled', 'publishing', 'published')
                ORDER BY id DESC
                LIMIT 1
                """,
                draft.target_chat_id,
                draft.content_hash,
                draft.id,
            )

            duplicate_post_row = None
            if text:
                duplicate_post_row = await connection.fetchrow(
                    """
                    SELECT message_id, message_url
                    FROM channel_posts
                    WHERE channel_id = $1::BIGINT
                      AND text_content = $2::TEXT
                    ORDER BY posted_at DESC
                    LIMIT 1
                    """,
                    draft.target_chat_id,
                    text,
                )

        return PublicationValidationContext(
            characters=tuple(
                PublicationCharacterInfo(
                    id=int(row["id"]),
                    name=str(row["name"]),
                    category=row["category"],
                    universe=row["universe"],
                    story_id=(int(row["story_id"]) if row["story_id"] is not None else None),
                    has_multi_story=bool(row["has_multi_story"]),
                    normalized_alias=str(row["normalized_alias"]),
                )
                for row in character_rows
            ),
            duplicate_draft=(
                DuplicateDraftInfo(
                    id=int(duplicate_draft_row["id"]),
                    status=str(duplicate_draft_row["status"]),
                )
                if duplicate_draft_row is not None
                else None
            ),
            duplicate_post=(
                DuplicatePostInfo(
                    message_id=int(duplicate_post_row["message_id"]),
                    message_url=duplicate_post_row["message_url"],
                )
                if duplicate_post_row is not None
                else None
            ),
        )

    async def save_result(
        self,
        draft: PublicationDraft,
        *,
        owner_id: int,
        post_type: str,
        issues: list[PublicationIssue],
    ) -> PublicationDraft:
        error_count = sum(issue.severity == "error" for issue in issues)
        warning_count = sum(issue.severity == "warning" for issue in issues)
        validation_status = (
            "failed" if error_count else ("warning" if warning_count else "passed")
        )
        status = draft.status
        if status in {"draft", "checked", "error"}:
            status = "checked"

        async with self._database._require_pool().acquire() as connection:
            async with connection.transaction():
                result = await connection.execute(
                    """
                    UPDATE publication_drafts
                    SET status = $2::VARCHAR,
                        post_type = $3::VARCHAR,
                        validation_status = $4::VARCHAR,
                        validation_error_count = $5::INTEGER,
                        validation_warning_count = $6::INTEGER,
                        validation_report = $7::JSONB,
                        last_error = CASE
                            WHEN status = 'error' THEN NULL
                            ELSE last_error
                        END,
                        updated_at = NOW()
                    WHERE id = $1::BIGINT
                      AND owner_id = $8::BIGINT
                    """,
                    draft.id,
                    status,
                    post_type,
                    validation_status,
                    error_count,
                    warning_count,
                    json.dumps(
                        [issue.as_dict() for issue in issues],
                        ensure_ascii=False,
                    ),
                    owner_id,
                )
                if result == "UPDATE 0":
                    raise ValueError("Черновик не найден.")
                await connection.execute(
                    """
                    INSERT INTO publication_events (
                        draft_id, event_type, actor_id, details
                    )
                    VALUES ($1::BIGINT, 'validated', $2::BIGINT, $3::JSONB)
                    """,
                    draft.id,
                    owner_id,
                    json.dumps(
                        {
                            "status": validation_status,
                            "errors": error_count,
                            "warnings": warning_count,
                        },
                        ensure_ascii=False,
                    ),
                )

        result_draft = await self._drafts.get_draft(draft.id, owner_id=owner_id)
        if result_draft is None:
            raise RuntimeError("Черновик исчез после проверки.")
        return result_draft


__all__ = ("PublicationValidationRepository",)

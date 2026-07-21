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
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID


class PublicationValidationRepository:
    """Read and persist validation data inside one workspace boundary."""

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
        async with self._database.acquire() as connection:
            character_rows = []
            if normalized_aliases and draft.workspace_id == DEFAULT_WORKSPACE_ID:
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
                    WHERE c.workspace_id = $1::BIGINT
                      AND a.normalized_alias = ANY($2::TEXT[])
                    """,
                    int(draft.workspace_id),
                    normalized_aliases,
                )
            elif normalized_aliases:
                character_rows = await connection.fetch(
                    """
                    SELECT DISTINCT
                        c.id,
                        c.name,
                        c.category,
                        c.universe,
                        (
                            SELECT link.story_id
                            FROM workspace_character_story_links AS link
                            WHERE link.workspace_id = c.workspace_id
                              AND link.character_id = c.id
                              AND link.is_primary
                            ORDER BY link.story_id
                            LIMIT 1
                        ) AS story_id,
                        EXISTS (
                            SELECT 1
                            FROM workspace_character_story_links AS link
                            WHERE link.workspace_id = c.workspace_id
                              AND link.character_id = c.id
                        ) AS has_multi_story,
                        a.normalized_alias
                    FROM workspace_character_aliases AS a
                    JOIN characters AS c
                      ON c.workspace_id = a.workspace_id
                     AND c.id = a.character_id
                    WHERE a.workspace_id = $1::BIGINT
                      AND a.normalized_alias = ANY($2::TEXT[])
                    """,
                    int(draft.workspace_id),
                    normalized_aliases,
                )

            duplicate_draft_row = await connection.fetchrow(
                """
                SELECT id, status
                FROM publication_drafts
                WHERE workspace_id = $1::BIGINT
                  AND target_chat_id = $2::BIGINT
                  AND content_hash = $3::CHAR(64)
                  AND id <> $4::BIGINT
                  AND status IN ('scheduled', 'publishing', 'published')
                ORDER BY id DESC
                LIMIT 1
                """,
                int(draft.workspace_id),
                int(draft.target_chat_id),
                draft.content_hash,
                int(draft.id),
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
                    int(draft.target_chat_id),
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

        async with self._database.acquire() as connection:
            async with connection.transaction():
                result = await connection.execute(
                    """
                    UPDATE publication_drafts
                    SET status = $4::VARCHAR,
                        post_type = $5::VARCHAR,
                        validation_status = $6::VARCHAR,
                        validation_error_count = $7::INTEGER,
                        validation_warning_count = $8::INTEGER,
                        validation_report = $9::JSONB,
                        last_error = CASE
                            WHEN status = 'error' THEN NULL
                            ELSE last_error
                        END,
                        updated_at = NOW()
                    WHERE workspace_id = $1::BIGINT
                      AND id = $2::BIGINT
                      AND ($1::BIGINT <> 1 OR owner_id = $3::BIGINT)
                    """,
                    int(draft.workspace_id),
                    int(draft.id),
                    int(owner_id),
                    status,
                    post_type,
                    validation_status,
                    error_count,
                    warning_count,
                    json.dumps(
                        [issue.as_dict() for issue in issues],
                        ensure_ascii=False,
                    ),
                )
                if result == "UPDATE 0":
                    raise ValueError("Черновик не найден в выбранном пространстве.")
                await connection.execute(
                    """
                    INSERT INTO publication_events (
                        workspace_id, draft_id, event_type, actor_id, details
                    )
                    VALUES (
                        $1::BIGINT, $2::BIGINT, 'validated', $3::BIGINT, $4::JSONB
                    )
                    """,
                    int(draft.workspace_id),
                    int(draft.id),
                    int(owner_id),
                    json.dumps(
                        {
                            "status": validation_status,
                            "errors": error_count,
                            "warnings": warning_count,
                        },
                        ensure_ascii=False,
                    ),
                )

        result_draft = await self._drafts.get_draft(
            draft.id,
            owner_id=owner_id,
            workspace_id=draft.workspace_id,
        )
        if result_draft is None:
            raise RuntimeError("Черновик исчез после проверки.")
        return result_draft


__all__ = ("PublicationValidationRepository",)

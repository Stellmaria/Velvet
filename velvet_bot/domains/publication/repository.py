from __future__ import annotations

import json
from typing import Any

from velvet_bot.database import Database
from velvet_bot.domains.publication.models import (
    PublicationDraft,
    PublicationDraftPage,
    PublicationIssue,
    PublicationItem,
)


class PublicationRepository:
    """PostgreSQL boundary for publication drafts, events and queue transitions."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def get_draft(
        self,
        draft_id: int,
        *,
        owner_id: int | None = None,
    ) -> PublicationDraft | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT *
                FROM publication_drafts
                WHERE id = $1::BIGINT
                  AND ($2::BIGINT IS NULL OR owner_id = $2::BIGINT)
                """,
                int(draft_id),
                owner_id,
            )
            if row is None:
                return None
            item_rows = await connection.fetch(
                """
                SELECT *
                FROM publication_draft_items
                WHERE draft_id = $1::BIGINT
                ORDER BY position
                """,
                int(draft_id),
            )
        return self._row_to_draft(row, item_rows)

    async def list_drafts(
        self,
        *,
        owner_id: int,
        statuses: tuple[str, ...],
        page: int = 0,
        page_size: int = 6,
    ) -> PublicationDraftPage:
        safe_size = max(1, min(int(page_size), 10))
        safe_page = max(0, int(page))
        async with self._database.acquire() as connection:
            total = int(
                await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM publication_drafts
                    WHERE owner_id = $1::BIGINT
                      AND status = ANY($2::VARCHAR[])
                    """,
                    int(owner_id),
                    list(statuses),
                )
                or 0
            )
            total_pages = max(1, (total + safe_size - 1) // safe_size)
            normalized_page = min(safe_page, total_pages - 1)
            rows = await connection.fetch(
                """
                SELECT *
                FROM publication_drafts
                WHERE owner_id = $1::BIGINT
                  AND status = ANY($2::VARCHAR[])
                ORDER BY COALESCE(scheduled_at, updated_at) DESC, id DESC
                OFFSET $3::INTEGER LIMIT $4::INTEGER
                """,
                int(owner_id),
                list(statuses),
                normalized_page * safe_size,
                safe_size,
            )
            drafts: list[PublicationDraft] = []
            for row in rows:
                item_rows = await connection.fetch(
                    """
                    SELECT *
                    FROM publication_draft_items
                    WHERE draft_id = $1::BIGINT
                    ORDER BY position
                    """,
                    int(row["id"]),
                )
                drafts.append(self._row_to_draft(row, item_rows))
        return PublicationDraftPage(
            items=tuple(drafts),
            page=normalized_page,
            page_size=safe_size,
            total_items=total,
        )

    async def claim_for_publishing(self, draft_id: int) -> bool:
        async with self._database.acquire() as connection:
            status = await connection.execute(
                """
                UPDATE publication_drafts
                SET status = 'publishing',
                    attempt_count = attempt_count + 1,
                    last_error = NULL,
                    updated_at = NOW()
                WHERE id = $1::BIGINT
                  AND status IN ('draft', 'checked', 'scheduled', 'error')
                """,
                int(draft_id),
            )
        return status != "UPDATE 0"

    async def mark_published(
        self,
        draft_id: int,
        *,
        message_ids: list[int],
        actor_id: int | None,
    ) -> None:
        details = json.dumps({"message_ids": message_ids}, ensure_ascii=False)
        async with self._database.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE publication_drafts
                    SET status = 'published',
                        published_at = NOW(),
                        published_message_ids = $2::BIGINT[],
                        scheduled_at = NULL,
                        last_error = NULL,
                        updated_at = NOW()
                    WHERE id = $1::BIGINT
                    """,
                    int(draft_id),
                    [int(value) for value in message_ids],
                )
                await self._log_event_on_connection(
                    connection,
                    draft_id=int(draft_id),
                    event_type="published",
                    actor_id=actor_id,
                    details_json=details,
                )

    async def mark_error(
        self,
        draft_id: int,
        *,
        error: Exception | str,
        actor_id: int | None,
    ) -> None:
        message = str(error)[:4000]
        details = json.dumps({"error": message}, ensure_ascii=False)
        async with self._database.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE publication_drafts
                    SET status = 'error',
                        last_error = $2::TEXT,
                        updated_at = NOW()
                    WHERE id = $1::BIGINT
                    """,
                    int(draft_id),
                    message,
                )
                await self._log_event_on_connection(
                    connection,
                    draft_id=int(draft_id),
                    event_type="error",
                    actor_id=actor_id,
                    details_json=details,
                )

    async def list_due_draft_ids(self, *, limit: int = 5) -> list[int]:
        safe_limit = max(1, min(int(limit), 20))
        async with self._database.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE publication_drafts
                    SET status = 'error',
                        last_error = COALESCE(
                            last_error,
                            'Публикация зависла и была остановлена.'
                        ),
                        updated_at = NOW()
                    WHERE status = 'publishing'
                      AND updated_at < NOW() - INTERVAL '15 minutes'
                    """
                )
                rows = await connection.fetch(
                    """
                    SELECT id
                    FROM publication_drafts
                    WHERE status = 'scheduled'
                      AND scheduled_at <= NOW()
                    ORDER BY scheduled_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT $1::INTEGER
                    """,
                    safe_limit,
                )
        return [int(row["id"]) for row in rows]

    @staticmethod
    async def _log_event_on_connection(
        connection,
        *,
        draft_id: int,
        event_type: str,
        actor_id: int | None,
        details_json: str,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO publication_events (
                draft_id, event_type, actor_id, details
            )
            VALUES ($1::BIGINT, $2::VARCHAR, $3::BIGINT, $4::JSONB)
            """,
            draft_id,
            event_type,
            actor_id,
            details_json,
        )

    @staticmethod
    def _row_to_issue(value: Any) -> PublicationIssue:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = {}
        value = value if isinstance(value, dict) else {}
        return PublicationIssue(
            code=str(value.get("code", "unknown")),
            severity=str(value.get("severity", "warning")),
            title=str(value.get("title", "Проверка")),
            detail=str(value.get("detail", "")),
        )

    @staticmethod
    def _row_to_item(row) -> PublicationItem:
        return PublicationItem(
            id=int(row["id"]),
            draft_id=int(row["draft_id"]),
            position=int(row["position"]),
            telegram_file_id=str(row["telegram_file_id"]),
            telegram_file_unique_id=row["telegram_file_unique_id"],
            media_type=str(row["media_type"]),
            mime_type=row["mime_type"],
            file_name=row["file_name"],
            file_size=(int(row["file_size"]) if row["file_size"] is not None else None),
            source_message_id=row["source_message_id"],
            has_spoiler=bool(row["has_spoiler"]),
        )

    @classmethod
    def _row_to_draft(cls, row, item_rows) -> PublicationDraft:
        raw_report = row["validation_report"] or []
        if isinstance(raw_report, str):
            try:
                raw_report = json.loads(raw_report)
            except json.JSONDecodeError:
                raw_report = []
        return PublicationDraft(
            id=int(row["id"]),
            owner_id=int(row["owner_id"]),
            target_chat_id=int(row["target_chat_id"]),
            source_chat_id=row["source_chat_id"],
            source_message_id=row["source_message_id"],
            source_media_group_id=row["source_media_group_id"],
            text_content=str(row["text_content"] or ""),
            status=str(row["status"]),
            post_type=str(row["post_type"]),
            has_spoiler=bool(row["has_spoiler"]),
            content_hash=str(row["content_hash"]),
            validation_status=str(row["validation_status"]),
            validation_error_count=int(row["validation_error_count"] or 0),
            validation_warning_count=int(row["validation_warning_count"] or 0),
            validation_report=tuple(cls._row_to_issue(value) for value in raw_report),
            scheduled_at=row["scheduled_at"],
            published_at=row["published_at"],
            published_message_ids=tuple(
                int(value) for value in (row["published_message_ids"] or [])
            ),
            attempt_count=int(row["attempt_count"] or 0),
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            items=tuple(cls._row_to_item(item) for item in item_rows),
        )


__all__ = ("PublicationRepository",)

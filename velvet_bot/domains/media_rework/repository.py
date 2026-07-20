from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from velvet_bot.database import Database

_ACTIVE_STATUSES = ("needs_fix", "checking", "ready_for_review")


@dataclass(frozen=True, slots=True)
class MediaReworkSummary:
    active: int
    needs_fix: int
    checking: int
    ready_for_review: int


@dataclass(frozen=True, slots=True)
class MediaReworkItem:
    media_id: int
    file_name: str
    media_type: str
    telegram_file_id: str
    preview_file_id: str | None
    status: str
    source: str
    reason: str | None
    qwen_verdict: str | None
    qwen_score: int | None
    quality_report: dict[str, Any] | None
    character_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MediaReworkPage:
    items: tuple[MediaReworkItem, ...]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)


def _decode_json(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None
    return None


class MediaReworkRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    @staticmethod
    def _item_from_row(row: Any) -> MediaReworkItem:
        names = row["character_names"] or []
        return MediaReworkItem(
            media_id=int(row["media_id"]),
            file_name=str(row["file_name"] or f"media-{row['media_id']}"),
            media_type=str(row["media_type"]),
            telegram_file_id=str(row["telegram_file_id"]),
            preview_file_id=(
                str(row["preview_file_id"])
                if row["preview_file_id"] is not None
                else None
            ),
            status=str(row["status"]),
            source=str(row["source"]),
            reason=str(row["reason"]) if row["reason"] is not None else None,
            qwen_verdict=(
                str(row["qwen_verdict"])
                if row["qwen_verdict"] is not None
                else None
            ),
            qwen_score=(
                int(row["qwen_score"])
                if row["qwen_score"] is not None
                else None
            ),
            quality_report=_decode_json(row["quality_report"]),
            character_names=tuple(str(name) for name in names),
        )

    async def summary(self) -> MediaReworkSummary:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE status IN ('needs_fix', 'checking', 'ready_for_review')
                    ) AS active,
                    COUNT(*) FILTER (WHERE status = 'needs_fix') AS needs_fix,
                    COUNT(*) FILTER (WHERE status = 'checking') AS checking,
                    COUNT(*) FILTER (
                        WHERE status = 'ready_for_review'
                    ) AS ready_for_review
                FROM media_rework_items
                """
            )
        return MediaReworkSummary(
            active=int(row["active"] or 0),
            needs_fix=int(row["needs_fix"] or 0),
            checking=int(row["checking"] or 0),
            ready_for_review=int(row["ready_for_review"] or 0),
        )

    async def list_active(
        self,
        *,
        page: int = 0,
        page_size: int = 6,
    ) -> MediaReworkPage:
        safe_size = max(1, min(int(page_size), 10))
        async with self._database.acquire() as connection:
            total = int(
                await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM media_rework_items
                    WHERE status IN ('needs_fix', 'checking', 'ready_for_review')
                    """
                )
                or 0
            )
            total_pages = max(1, (total + safe_size - 1) // safe_size)
            safe_page = min(max(0, int(page)), total_pages - 1)
            rows = await connection.fetch(
                """
                SELECT
                    r.*,
                    COALESCE(mf.original_file_name, mf.storage_file_name) AS file_name,
                    mf.media_type,
                    mf.telegram_file_id,
                    mf.preview_file_id,
                    q.report AS quality_report,
                    ARRAY_REMOVE(ARRAY_AGG(DISTINCT c.name), NULL) AS character_names
                FROM media_rework_items AS r
                JOIN media_files AS mf ON mf.id = r.media_id
                LEFT JOIN media_ai_quality_checks AS q ON q.media_id = r.media_id
                LEFT JOIN character_media AS cm ON cm.media_id = r.media_id
                LEFT JOIN characters AS c ON c.id = cm.character_id
                WHERE r.status IN ('needs_fix', 'checking', 'ready_for_review')
                GROUP BY r.media_id, mf.id, q.media_id
                ORDER BY
                    CASE r.status
                        WHEN 'needs_fix' THEN 3
                        WHEN 'ready_for_review' THEN 2
                        ELSE 1
                    END DESC,
                    r.updated_at DESC,
                    r.media_id DESC
                OFFSET $1::INTEGER LIMIT $2::INTEGER
                """,
                safe_page * safe_size,
                safe_size,
            )
        return MediaReworkPage(
            items=tuple(self._item_from_row(row) for row in rows),
            page=safe_page,
            page_size=safe_size,
            total_items=total,
        )

    async def get_item(self, media_id: int) -> MediaReworkItem | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    r.*,
                    COALESCE(mf.original_file_name, mf.storage_file_name) AS file_name,
                    mf.media_type,
                    mf.telegram_file_id,
                    mf.preview_file_id,
                    q.report AS quality_report,
                    ARRAY_REMOVE(ARRAY_AGG(DISTINCT c.name), NULL) AS character_names
                FROM media_rework_items AS r
                JOIN media_files AS mf ON mf.id = r.media_id
                LEFT JOIN media_ai_quality_checks AS q ON q.media_id = r.media_id
                LEFT JOIN character_media AS cm ON cm.media_id = r.media_id
                LEFT JOIN characters AS c ON c.id = cm.character_id
                WHERE r.media_id = $1::BIGINT
                GROUP BY r.media_id, mf.id, q.media_id
                """,
                int(media_id),
            )
        return self._item_from_row(row) if row is not None else None

    async def accept(self, media_id: int, user_id: int) -> bool:
        return await self._resolve(
            media_id=media_id,
            user_id=user_id,
            status="accepted",
            action="accepted",
        )

    async def dismiss(self, media_id: int, user_id: int) -> bool:
        return await self._resolve(
            media_id=media_id,
            user_id=user_id,
            status="dismissed",
            action="dismissed",
        )

    async def _resolve(
        self,
        *,
        media_id: int,
        user_id: int,
        status: str,
        action: str,
    ) -> bool:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE media_rework_items
                    SET status = $2::VARCHAR,
                        last_action_by = $3::BIGINT,
                        resolved_at = NOW(),
                        updated_at = NOW()
                    WHERE media_id = $1::BIGINT
                      AND status IN ('needs_fix', 'checking', 'ready_for_review')
                    RETURNING source
                    """,
                    int(media_id),
                    status,
                    int(user_id),
                )
                if row is None:
                    return False
                if status == "accepted":
                    await connection.execute(
                        """
                        UPDATE media_ai_quality_checks
                        SET decision = 'accepted',
                            decided_by = $2::BIGINT,
                            decided_at = NOW(),
                            updated_at = NOW()
                        WHERE media_id = $1::BIGINT
                          AND status = 'ready'
                        """,
                        int(media_id),
                        int(user_id),
                    )
                await connection.execute(
                    """
                    INSERT INTO media_rework_events (
                        media_id, action, source, actor_user_id
                    ) VALUES ($1::BIGINT, $2::VARCHAR, 'admin', $3::BIGINT)
                    """,
                    int(media_id),
                    action,
                    int(user_id),
                )
        return True

    async def retry(self, media_id: int, user_id: int) -> bool:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    UPDATE media_rework_items
                    SET status = 'checking',
                        last_action_by = $2::BIGINT,
                        resolved_at = NULL,
                        updated_at = NOW()
                    WHERE media_id = $1::BIGINT
                      AND status IN ('needs_fix', 'ready_for_review')
                    RETURNING media_id
                    """,
                    int(media_id),
                    int(user_id),
                )
                if row is None:
                    return False
                await connection.execute(
                    """
                    INSERT INTO media_ai_quality_checks AS q (
                        media_id, status, attempt_count, updated_at
                    )
                    VALUES ($1::BIGINT, 'pending', 0, NOW())
                    ON CONFLICT (media_id) DO UPDATE
                    SET status = 'pending',
                        attempt_count = 0,
                        verdict = NULL,
                        quality_score = NULL,
                        confidence = NULL,
                        report = NULL,
                        decision = NULL,
                        decided_by = NULL,
                        decided_at = NULL,
                        error_message = NULL,
                        analyzed_at = NULL,
                        updated_at = NOW()
                    """,
                    int(media_id),
                )
                await connection.execute(
                    """
                    INSERT INTO media_rework_events (
                        media_id, action, source, actor_user_id
                    ) VALUES ($1::BIGINT, 'recheck_requested', 'admin', $2::BIGINT)
                    """,
                    int(media_id),
                    int(user_id),
                )
        return True


__all__ = (
    "MediaReworkItem",
    "MediaReworkPage",
    "MediaReworkRepository",
    "MediaReworkSummary",
)

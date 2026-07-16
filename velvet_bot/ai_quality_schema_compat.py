from __future__ import annotations

from typing import Any

from velvet_bot.ai_quality import (
    AIQualityItem,
    AIQualityPage,
    AIQualityRepository,
    _decode_report,
)

_INSTALLED = False


def _item_from_row(row: Any) -> AIQualityItem:
    media_id = int(row["media_id"])
    media_type = str(row["media_type"])
    mime_type = str(row["mime_type"] or "").strip() if "mime_type" in row else ""
    display_name = f"media-{media_id}"
    if mime_type:
        display_name += f" · {mime_type}"
    elif media_type:
        display_name += f" · {media_type}"

    return AIQualityItem(
        media_id=media_id,
        file_name=display_name,
        media_type=media_type,
        telegram_file_id=str(row["telegram_file_id"]),
        preview_file_id=(
            str(row["preview_file_id"])
            if row["preview_file_id"] is not None
            else None
        ),
        status=str(row["status"]),
        verdict=str(row["verdict"]) if row["verdict"] is not None else None,
        quality_score=(
            int(row["quality_score"])
            if row["quality_score"] is not None
            else None
        ),
        confidence=int(row["confidence"]) if row["confidence"] is not None else None,
        report=_decode_report(row["report"]),
        decision=str(row["decision"]) if row["decision"] is not None else None,
        error_message=(
            str(row["error_message"])
            if row["error_message"] is not None
            else None
        ),
    )


async def _list_items(
    self: AIQualityRepository,
    section: str,
    *,
    page: int = 0,
    page_size: int = 6,
) -> AIQualityPage:
    condition = self._section_condition(section)
    safe_size = max(1, min(int(page_size), 10))
    async with self._database._require_pool().acquire() as connection:
        total = int(
            await connection.fetchval(
                f"SELECT COUNT(*) FROM media_ai_quality_checks q WHERE {condition}"
            )
            or 0
        )
        total_pages = max(1, (total + safe_size - 1) // safe_size)
        safe_page = min(max(0, int(page)), total_pages - 1)
        offset = safe_page * safe_size
        rows = await connection.fetch(
            f"""
            SELECT q.*, mf.media_type, mf.mime_type, mf.telegram_file_id,
                   mf.preview_file_id
            FROM media_ai_quality_checks q
            JOIN media_files mf ON mf.id = q.media_id
            WHERE {condition}
            ORDER BY CASE q.verdict
                        WHEN 'critical' THEN 3
                        WHEN 'review' THEN 2
                        ELSE 1
                     END DESC,
                     q.updated_at DESC,
                     q.media_id DESC
            OFFSET $1::INTEGER LIMIT $2::INTEGER
            """,
            offset,
            safe_size,
        )
    return AIQualityPage(
        items=tuple(_item_from_row(row) for row in rows),
        page=safe_page,
        page_size=safe_size,
        total_items=total,
    )


async def _get_item(
    self: AIQualityRepository,
    media_id: int,
) -> AIQualityItem | None:
    async with self._database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT q.*, mf.media_type, mf.mime_type, mf.telegram_file_id,
                   mf.preview_file_id
            FROM media_ai_quality_checks q
            JOIN media_files mf ON mf.id = q.media_id
            WHERE q.media_id = $1::BIGINT
            """,
            int(media_id),
        )
    return _item_from_row(row) if row is not None else None


def install_ai_quality_schema_compatibility() -> None:
    """Adapt phase-1 quality UI to the real media_files schema.

    The production table never had a file_name column. Keep the public item field for
    UI compatibility, but derive a stable label from media id and MIME type instead.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    AIQualityRepository._item_from_row = staticmethod(_item_from_row)
    AIQualityRepository.list_items = _list_items
    AIQualityRepository.get_item = _get_item
    _INSTALLED = True


__all__ = ("install_ai_quality_schema_compatibility",)

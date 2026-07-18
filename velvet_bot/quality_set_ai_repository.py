from __future__ import annotations

import json
from dataclasses import dataclass

from velvet_bot.database import Database


@dataclass(frozen=True, slots=True)
class SetMediaItem:
    media_id: int
    telegram_file_id: str
    preview_file_id: str | None
    media_type: str
    file_name: str
    characters: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MediaSetBundle:
    id: int
    title: str
    items: tuple[SetMediaItem, ...]


@dataclass(frozen=True, slots=True)
class SetReportListItem:
    set_id: int
    title: str
    item_count: int
    report_id: int | None
    verdict: str | None
    overall_score: int | None


@dataclass(frozen=True, slots=True)
class SetReportPage:
    items: tuple[SetReportListItem, ...]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)


async def _load_set(database: Database, set_id: int) -> MediaSetBundle | None:
    async with database.acquire() as connection:
        header = await connection.fetchrow(
            """
            SELECT id, title
            FROM media_sets
            WHERE id = $1::BIGINT
            """,
            int(set_id),
        )
        if header is None:
            return None
        rows = await connection.fetch(
            """
            SELECT
                mf.id AS media_id,
                mf.telegram_file_id,
                mf.preview_file_id,
                mf.media_type,
                COALESCE(mf.original_file_name, mf.storage_file_name,
                         'media-' || mf.id::TEXT) AS file_name,
                COALESCE(
                    ARRAY_AGG(DISTINCT c.name ORDER BY c.name)
                        FILTER (WHERE c.id IS NOT NULL),
                    ARRAY[]::VARCHAR[]
                ) AS characters
            FROM media_files AS mf
            LEFT JOIN character_media AS cm ON cm.media_id = mf.id
            LEFT JOIN characters AS c ON c.id = cm.character_id
            WHERE mf.media_set_id = $1::BIGINT
              AND (
                    mf.media_type = 'photo'
                    OR (mf.media_type = 'document'
                        AND COALESCE(mf.mime_type, '') LIKE 'image/%')
                  )
            GROUP BY mf.id, mf.telegram_file_id, mf.preview_file_id,
                     mf.media_type, mf.original_file_name, mf.storage_file_name
            ORDER BY mf.id
            LIMIT 13
            """,
            int(set_id),
        )
    items = tuple(
        SetMediaItem(
            media_id=int(row["media_id"]),
            telegram_file_id=str(row["telegram_file_id"]),
            preview_file_id=(
                str(row["preview_file_id"])
                if row["preview_file_id"] is not None
                else None
            ),
            media_type=str(row["media_type"]),
            file_name=str(row["file_name"]),
            characters=tuple(str(value) for value in row["characters"] if value),
        )
        for row in rows
    )
    return MediaSetBundle(id=int(header["id"]), title=str(header["title"]), items=items)


async def _list_sets(
    database: Database,
    *,
    page: int,
    page_size: int = 6,
) -> SetReportPage:
    safe_size = max(1, min(int(page_size), 8))
    async with database.acquire() as connection:
        total = int(
            await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT mf.media_set_id
                    FROM media_files AS mf
                    WHERE mf.media_set_id IS NOT NULL
                      AND (
                            mf.media_type = 'photo'
                            OR (mf.media_type = 'document'
                                AND COALESCE(mf.mime_type, '') LIKE 'image/%')
                          )
                    GROUP BY mf.media_set_id
                    HAVING COUNT(*) >= 2
                ) AS eligible
                """
            )
            or 0
        )
        total_pages = max(1, (total + safe_size - 1) // safe_size)
        safe_page = min(max(0, int(page)), total_pages - 1)
        rows = await connection.fetch(
            """
            SELECT
                ms.id AS set_id,
                ms.title,
                COUNT(mf.id)::INTEGER AS item_count,
                latest.id AS report_id,
                latest.verdict,
                latest.overall_score
            FROM media_sets AS ms
            JOIN media_files AS mf
              ON mf.media_set_id = ms.id
             AND (
                    mf.media_type = 'photo'
                    OR (mf.media_type = 'document'
                        AND COALESCE(mf.mime_type, '') LIKE 'image/%')
                 )
            LEFT JOIN LATERAL (
                SELECT report.id, report.verdict, report.overall_score,
                       report.created_at
                FROM media_set_ai_reports AS report
                WHERE report.media_set_id = ms.id
                ORDER BY report.created_at DESC, report.id DESC
                LIMIT 1
            ) AS latest ON TRUE
            GROUP BY ms.id, ms.title, latest.id, latest.verdict,
                     latest.overall_score, latest.created_at
            HAVING COUNT(mf.id) >= 2
            ORDER BY latest.created_at DESC NULLS LAST, ms.id DESC
            OFFSET $1::INTEGER LIMIT $2::INTEGER
            """,
            safe_page * safe_size,
            safe_size,
        )
    return SetReportPage(
        items=tuple(
            SetReportListItem(
                set_id=int(row["set_id"]),
                title=str(row["title"]),
                item_count=int(row["item_count"]),
                report_id=int(row["report_id"]) if row["report_id"] is not None else None,
                verdict=str(row["verdict"]) if row["verdict"] is not None else None,
                overall_score=(
                    int(row["overall_score"])
                    if row["overall_score"] is not None
                    else None
                ),
            )
            for row in rows
        ),
        page=safe_page,
        page_size=safe_size,
        total_items=total,
    )


async def _latest_report(
    database: Database,
    set_id: int,
) -> tuple[int, dict[str, object]] | None:
    async with database.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT id, report
            FROM media_set_ai_reports
            WHERE media_set_id = $1::BIGINT
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            int(set_id),
        )
    if row is None:
        return None
    value = row["report"]
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = None
    if not isinstance(value, dict):
        return None
    return int(row["id"]), value


async def _save_report(
    database: Database,
    *,
    set_id: int,
    provider: str,
    model: str,
    report: dict[str, object],
    created_by: int | None,
) -> int:
    async with database.acquire() as connection:
        value = await connection.fetchval(
            """
            INSERT INTO media_set_ai_reports (
                media_set_id, provider, model, analysis_version, item_count,
                overall_score, style_score, lighting_score, palette_score,
                environment_score, composition_score, narrative_score,
                character_continuity_score, technical_score, confidence,
                verdict, report, created_by
            )
            VALUES (
                $1::BIGINT, $2::VARCHAR, $3::VARCHAR, $4::SMALLINT, $5::SMALLINT,
                $6::SMALLINT, $7::SMALLINT, $8::SMALLINT, $9::SMALLINT,
                $10::SMALLINT, $11::SMALLINT, $12::SMALLINT, $13::SMALLINT,
                $14::SMALLINT, $15::SMALLINT, $16::VARCHAR, $17::JSONB, $18::BIGINT
            )
            RETURNING id
            """,
            int(set_id),
            provider[:64],
            model[:160],
            int(report.get("analysis_version") or 1),
            len(report.get("items") or []),
            int(report["overall_score"]),
            int(report["style_score"]),
            int(report["lighting_score"]),
            int(report["palette_score"]),
            int(report["environment_score"]),
            int(report["composition_score"]),
            int(report["narrative_score"]),
            int(report["character_continuity_score"]),
            int(report["technical_score"]),
            int(report["confidence"]),
            str(report["verdict"]),
            json.dumps(report, ensure_ascii=False),
            created_by,
        )
    return int(value)


__all__ = (
    "MediaSetBundle",
    "SetMediaItem",
    "SetReportListItem",
    "SetReportPage",
    "_latest_report",
    "_list_sets",
    "_load_set",
    "_save_report",
)

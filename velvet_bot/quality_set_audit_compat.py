from __future__ import annotations

from dataclasses import replace

import velvet_bot.quality_audit as quality_audit
from velvet_bot.database import Database
from velvet_bot.quality_audit import QualityItem, QualityPage, QualitySummary

_ORIGINAL_GET_QUALITY_SUMMARY = quality_audit.get_quality_summary
_ORIGINAL_LIST_MEDIA_ISSUES = quality_audit.list_media_issues


async def get_quality_summary_with_sets(database: Database) -> QualitySummary:
    summary = await _ORIGINAL_GET_QUALITY_SUMMARY(database)
    async with database._require_pool().acquire() as connection:
        without_prompt = int(
            await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM character_media AS cm
                JOIN media_files AS mf ON mf.id = cm.media_id
                LEFT JOIN media_sets AS ms ON ms.id = mf.media_set_id
                WHERE CASE
                    WHEN mf.media_set_id IS NOT NULL
                        THEN ms.prompt_post_url IS NULL
                    ELSE cm.prompt_post_url IS NULL
                END
                """
            )
            or 0
        )
    return replace(summary, media_without_prompt=without_prompt)


async def list_media_issues_with_sets(
    database: Database,
    section: str,
    *,
    page: int = 0,
    page_size: int = 8,
) -> QualityPage:
    if section != "media_without_prompt":
        return await _ORIGINAL_LIST_MEDIA_ISSUES(
            database,
            section,
            page=page,
            page_size=page_size,
        )

    async with database._require_pool().acquire() as connection:
        total = int(
            await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM character_media AS cm
                JOIN media_files AS mf ON mf.id = cm.media_id
                LEFT JOIN media_sets AS ms ON ms.id = mf.media_set_id
                WHERE CASE
                    WHEN mf.media_set_id IS NOT NULL
                        THEN ms.prompt_post_url IS NULL
                    ELSE cm.prompt_post_url IS NULL
                END
                """
            )
            or 0
        )
        safe_page, safe_size, offset = quality_audit._page_bounds(
            total,
            page,
            page_size,
        )
        rows = await connection.fetch(
            """
            SELECT
                c.id AS character_id,
                c.name AS character_name,
                c.category,
                mf.id AS media_id,
                COALESCE(mf.original_file_name, mf.storage_file_name) AS file_name,
                mf.media_type,
                mf.media_set_id,
                ms.title AS media_set_title,
                (
                    SELECT COUNT(*)
                    FROM character_media AS cm2
                    JOIN media_files AS mf2 ON mf2.id = cm2.media_id
                    WHERE cm2.character_id = c.id
                      AND (
                          cm2.created_at > cm.created_at
                          OR (cm2.created_at = cm.created_at AND mf2.id > mf.id)
                      )
                ) AS media_offset
            FROM character_media AS cm
            JOIN characters AS c ON c.id = cm.character_id
            JOIN media_files AS mf ON mf.id = cm.media_id
            LEFT JOIN media_sets AS ms ON ms.id = mf.media_set_id
            WHERE CASE
                WHEN mf.media_set_id IS NOT NULL
                    THEN ms.prompt_post_url IS NULL
                ELSE cm.prompt_post_url IS NULL
            END
            ORDER BY c.normalized_name, cm.created_at DESC, mf.id DESC
            OFFSET $1::INTEGER LIMIT $2::INTEGER
            """,
            offset,
            safe_size,
        )

    return QualityPage(
        items=tuple(
            QualityItem(
                id=int(row["media_id"]),
                label=f"{row['character_name']} · {row['file_name']}",
                detail=(
                    f"сет: {row['media_set_title']} · общий промт не привязан"
                    if row["media_set_id"] is not None
                    else str(row["media_type"])
                )[:180],
                character_id=int(row["character_id"]),
                category=row["category"],
                media_id=int(row["media_id"]),
                media_offset=int(row["media_offset"] or 0),
            )
            for row in rows
        ),
        page=safe_page,
        page_size=safe_size,
        total_items=total,
    )


def install_quality_set_audit() -> None:
    quality_audit.get_quality_summary = get_quality_summary_with_sets
    quality_audit.list_media_issues = list_media_issues_with_sets


install_quality_set_audit()

__all__ = (
    "get_quality_summary_with_sets",
    "install_quality_set_audit",
    "list_media_issues_with_sets",
)

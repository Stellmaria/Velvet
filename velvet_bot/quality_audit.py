from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.database import Database

STORY_REQUIRED_UNIVERSES = ("shs", "kr", "lm", "idm", "lagerta")


@dataclass(frozen=True, slots=True)
class QualitySummary:
    pending_duplicates: int
    confirmed_duplicates: int
    pending_scans: int
    scan_errors: int
    broken_files: int
    unchecked_files: int
    missing_category: int
    missing_universe: int
    missing_story: int
    empty_characters: int
    media_without_prompt: int
    orphan_media: int
    unresolved_hashtags: int

    @property
    def total_problems(self) -> int:
        return (
            self.pending_duplicates
            + self.scan_errors
            + self.broken_files
            + self.missing_category
            + self.missing_universe
            + self.missing_story
            + self.empty_characters
            + self.media_without_prompt
            + self.orphan_media
            + self.unresolved_hashtags
        )


@dataclass(frozen=True, slots=True)
class QualityItem:
    id: int
    label: str
    detail: str
    character_id: int | None = None
    category: str | None = None
    media_id: int | None = None
    media_offset: int | None = None


@dataclass(frozen=True, slots=True)
class QualityPage:
    items: tuple[QualityItem, ...]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)


async def get_quality_summary(database: Database) -> QualitySummary:
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM media_duplicate_candidates WHERE status = 'pending')
                    AS pending_duplicates,
                (SELECT COUNT(*) FROM media_duplicate_candidates WHERE status = 'confirmed')
                    AS confirmed_duplicates,
                (SELECT COUNT(*) FROM media_files WHERE visual_scan_status IN ('pending', 'processing'))
                    AS pending_scans,
                (SELECT COUNT(*) FROM media_files WHERE visual_scan_status = 'error')
                    AS scan_errors,
                (SELECT COUNT(*) FROM media_file_checks WHERE status = 'broken')
                    AS broken_files,
                (SELECT COUNT(*) FROM media_file_checks WHERE status = 'unknown')
                    AS unchecked_files,
                (SELECT COUNT(*) FROM characters WHERE category IS NULL)
                    AS missing_category,
                (SELECT COUNT(*) FROM characters WHERE universe IS NULL)
                    AS missing_universe,
                (SELECT COUNT(*)
                 FROM characters c
                 WHERE c.universe = ANY($1::TEXT[])
                   AND NOT EXISTS (
                       SELECT 1 FROM character_story_links l
                       WHERE l.character_id = c.id
                   )) AS missing_story,
                (SELECT COUNT(*)
                 FROM characters c
                 WHERE NOT EXISTS (
                     SELECT 1 FROM character_media cm WHERE cm.character_id = c.id
                 )) AS empty_characters,
                (SELECT COUNT(*) FROM character_media WHERE prompt_post_url IS NULL)
                    AS media_without_prompt,
                (SELECT COUNT(*)
                 FROM media_files mf
                 WHERE NOT EXISTS (
                     SELECT 1 FROM character_media cm WHERE cm.media_id = mf.id
                 )) AS orphan_media,
                (SELECT COUNT(DISTINCT normalized_hashtag)
                 FROM channel_post_hashtags WHERE character_id IS NULL)
                    AS unresolved_hashtags
            """,
            list(STORY_REQUIRED_UNIVERSES),
        )
    return QualitySummary(**{key: int(row[key] or 0) for key in row.keys()})


def _page_bounds(total: int, page: int, page_size: int) -> tuple[int, int, int]:
    safe_size = max(1, min(page_size, 10))
    total_pages = max(1, (total + safe_size - 1) // safe_size)
    safe_page = min(max(0, page), total_pages - 1)
    return safe_page, safe_size, safe_page * safe_size


async def list_character_issues(
    database: Database,
    section: str,
    *,
    page: int = 0,
    page_size: int = 8,
) -> QualityPage:
    filters = {
        "missing_category": "c.category IS NULL",
        "missing_universe": "c.universe IS NULL",
        "missing_story": "c.universe = ANY($1::TEXT[]) AND NOT EXISTS (SELECT 1 FROM character_story_links l WHERE l.character_id = c.id)",
        "empty_characters": "NOT EXISTS (SELECT 1 FROM character_media cm WHERE cm.character_id = c.id)",
    }
    condition = filters.get(section)
    if condition is None:
        raise ValueError("Неизвестный раздел персонажей.")
    args_prefix = [list(STORY_REQUIRED_UNIVERSES)] if "$1" in condition else []
    async with database._require_pool().acquire() as connection:
        total = int(
            await connection.fetchval(
                f"SELECT COUNT(*) FROM characters c WHERE {condition}",
                *args_prefix,
            )
            or 0
        )
        safe_page, safe_size, offset = _page_bounds(total, page, page_size)
        offset_position = len(args_prefix) + 1
        limit_position = offset_position + 1
        rows = await connection.fetch(
            f"""
            SELECT c.id, c.name, c.category, c.universe,
                   COUNT(cm.media_id) AS media_count
            FROM characters c
            LEFT JOIN character_media cm ON cm.character_id = c.id
            WHERE {condition}
            GROUP BY c.id
            ORDER BY c.normalized_name
            OFFSET ${offset_position} LIMIT ${limit_position}
            """,
            *args_prefix,
            offset,
            safe_size,
        )
    return QualityPage(
        items=tuple(
            QualityItem(
                id=int(row["id"]),
                label=str(row["name"]),
                detail=(
                    f"категория: {row['category'] or '—'} · "
                    f"вселенная: {row['universe'] or '—'} · "
                    f"материалов: {int(row['media_count'] or 0)}"
                ),
                character_id=int(row["id"]),
                category=row["category"],
            )
            for row in rows
        ),
        page=safe_page,
        page_size=safe_size,
        total_items=total,
    )


async def list_media_issues(
    database: Database,
    section: str,
    *,
    page: int = 0,
    page_size: int = 8,
) -> QualityPage:
    conditions = {
        "media_without_prompt": "cm.prompt_post_url IS NULL",
        "broken_files": "fc.status = 'broken'",
        "scan_errors": "mf.visual_scan_status = 'error'",
    }
    condition = conditions.get(section)
    if condition is None:
        raise ValueError("Неизвестный раздел медиа.")
    async with database._require_pool().acquire() as connection:
        total = int(
            await connection.fetchval(
                f"""
                SELECT COUNT(*)
                FROM character_media cm
                JOIN characters c ON c.id = cm.character_id
                JOIN media_files mf ON mf.id = cm.media_id
                JOIN media_file_checks fc ON fc.media_id = mf.id
                WHERE {condition}
                """
            )
            or 0
        )
        safe_page, safe_size, offset = _page_bounds(total, page, page_size)
        rows = await connection.fetch(
            f"""
            SELECT c.id AS character_id, c.name AS character_name, c.category,
                   mf.id AS media_id,
                   COALESCE(mf.original_file_name, mf.storage_file_name) AS file_name,
                   mf.media_type, mf.visual_scan_error, fc.error_text,
                   ROW_NUMBER() OVER (
                       PARTITION BY c.id ORDER BY cm.created_at DESC, mf.id DESC
                   ) - 1 AS media_offset
            FROM character_media cm
            JOIN characters c ON c.id = cm.character_id
            JOIN media_files mf ON mf.id = cm.media_id
            JOIN media_file_checks fc ON fc.media_id = mf.id
            WHERE {condition}
            ORDER BY c.normalized_name, cm.created_at DESC, mf.id DESC
            OFFSET $1 LIMIT $2
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
                    str(row["visual_scan_error"] or row["error_text"] or row["media_type"])
                )[:180],
                character_id=int(row["character_id"]),
                category=row["category"],
                media_id=int(row["media_id"]),
                media_offset=int(row["media_offset"]),
            )
            for row in rows
        ),
        page=safe_page,
        page_size=safe_size,
        total_items=total,
    )


async def list_unresolved_hashtags(
    database: Database,
    *,
    page: int = 0,
    page_size: int = 8,
) -> QualityPage:
    async with database._require_pool().acquire() as connection:
        total = int(
            await connection.fetchval(
                "SELECT COUNT(DISTINCT normalized_hashtag) FROM channel_post_hashtags WHERE character_id IS NULL"
            )
            or 0
        )
        safe_page, safe_size, offset = _page_bounds(total, page, page_size)
        rows = await connection.fetch(
            """
            SELECT normalized_hashtag, MAX(hashtag) AS hashtag,
                   COUNT(DISTINCT post_id) AS use_count
            FROM channel_post_hashtags
            WHERE character_id IS NULL
            GROUP BY normalized_hashtag
            ORDER BY use_count DESC, normalized_hashtag
            OFFSET $1 LIMIT $2
            """,
            offset,
            safe_size,
        )
    return QualityPage(
        items=tuple(
            QualityItem(
                id=index + offset + 1,
                label=f"#{row['hashtag']}",
                detail=f"использований: {int(row['use_count'] or 0)}",
            )
            for index, row in enumerate(rows)
        ),
        page=safe_page,
        page_size=safe_size,
        total_items=total,
    )


async def remove_orphan_media(database: Database) -> int:
    async with database._require_pool().acquire() as connection:
        result = await connection.execute(
            """
            DELETE FROM media_files mf
            WHERE NOT EXISTS (
                SELECT 1 FROM character_media cm WHERE cm.media_id = mf.id
            )
            """
        )
    return int(result.split()[-1])


async def reset_broken_file_checks(database: Database) -> int:
    async with database._require_pool().acquire() as connection:
        result = await connection.execute(
            """
            UPDATE media_file_checks
            SET status = 'unknown', error_text = NULL, checked_at = NULL, updated_at = NOW()
            WHERE status = 'broken'
            """
        )
    return int(result.split()[-1])

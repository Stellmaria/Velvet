from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from velvet_bot.database import Database
from velvet_bot.visual_fingerprint import (
    FingerprintComparison,
    VisualFingerprint,
    build_visual_fingerprint,
    compare_fingerprints,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MediaScanTarget:
    media_id: int
    telegram_file_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class StoredFingerprint:
    media_id: int
    fingerprint: VisualFingerprint


@dataclass(frozen=True, slots=True)
class DuplicateCandidate:
    id: int
    first_media_id: int
    second_media_id: int
    similarity_score: int
    phash_distance: int
    center_distance: int
    dhash_distance: int
    ahash_distance: int
    exact_bytes: bool
    status: str
    first_file_name: str
    second_file_name: str
    first_file_id: str
    second_file_id: str
    first_media_type: str
    second_media_type: str
    first_mime_type: str | None
    second_mime_type: str | None
    first_characters: tuple[str, ...]
    second_characters: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DuplicatePage:
    items: tuple[DuplicateCandidate, ...]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)


def _row_to_fingerprint(row) -> StoredFingerprint:
    return StoredFingerprint(
        media_id=int(row["media_id"]),
        fingerprint=VisualFingerprint(
            content_sha256=str(row["content_sha256"]),
            phash=str(row["phash"]),
            center_phash=str(row["center_phash"]),
            dhash=str(row["dhash"]),
            ahash=str(row["ahash"]),
            width=int(row["width"]),
            height=int(row["height"]),
            image_format=row["image_format"],
            version=int(row["fingerprint_version"]),
        ),
    )


async def _claim_pending_images(
    database: Database,
    *,
    limit: int = 2,
) -> list[MediaScanTarget]:
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            rows = await connection.fetch(
                """
                SELECT id, telegram_file_id,
                       COALESCE(original_file_name, storage_file_name) AS display_name
                FROM media_files
                WHERE visual_scan_status = 'pending'
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT $1
                """,
                max(1, min(limit, 5)),
            )
            if rows:
                await connection.execute(
                    """
                    UPDATE media_files
                    SET visual_scan_status = 'processing',
                        visual_scan_error = NULL
                    WHERE id = ANY($1::BIGINT[])
                    """,
                    [int(row["id"]) for row in rows],
                )
    return [
        MediaScanTarget(
            media_id=int(row["id"]),
            telegram_file_id=str(row["telegram_file_id"]),
            display_name=str(row["display_name"]),
        )
        for row in rows
    ]


async def _load_other_fingerprints(
    database: Database,
    media_id: int,
) -> list[StoredFingerprint]:
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT media_id, fingerprint_version, content_sha256,
                   phash, center_phash, dhash, ahash,
                   width, height, image_format
            FROM media_visual_fingerprints
            WHERE media_id <> $1
            """,
            media_id,
        )
    return [_row_to_fingerprint(row) for row in rows]


async def _store_fingerprint_and_candidates(
    database: Database,
    media_id: int,
    fingerprint: VisualFingerprint,
    comparisons: list[tuple[int, FingerprintComparison]],
) -> None:
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                """
                INSERT INTO media_visual_fingerprints (
                    media_id, fingerprint_version, content_sha256,
                    phash, center_phash, dhash, ahash,
                    width, height, image_format, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                ON CONFLICT (media_id) DO UPDATE
                SET fingerprint_version = EXCLUDED.fingerprint_version,
                    content_sha256 = EXCLUDED.content_sha256,
                    phash = EXCLUDED.phash,
                    center_phash = EXCLUDED.center_phash,
                    dhash = EXCLUDED.dhash,
                    ahash = EXCLUDED.ahash,
                    width = EXCLUDED.width,
                    height = EXCLUDED.height,
                    image_format = EXCLUDED.image_format,
                    updated_at = NOW()
                """,
                media_id,
                fingerprint.version,
                fingerprint.content_sha256,
                fingerprint.phash,
                fingerprint.center_phash,
                fingerprint.dhash,
                fingerprint.ahash,
                fingerprint.width,
                fingerprint.height,
                fingerprint.image_format,
            )
            await connection.execute(
                """
                UPDATE media_files
                SET visual_scan_status = 'ready',
                    visual_scan_error = NULL,
                    visual_scanned_at = NOW()
                WHERE id = $1
                """,
                media_id,
            )
            await connection.execute(
                """
                INSERT INTO media_file_checks (media_id, status, checked_at, error_text, updated_at)
                VALUES ($1, 'ok', NOW(), NULL, NOW())
                ON CONFLICT (media_id) DO UPDATE
                SET status = 'ok', checked_at = NOW(), error_text = NULL, updated_at = NOW()
                """,
                media_id,
            )
            for other_media_id, comparison in comparisons:
                first_id, second_id = sorted((media_id, other_media_id))
                await connection.execute(
                    """
                    INSERT INTO media_duplicate_candidates (
                        first_media_id, second_media_id,
                        similarity_score, phash_distance, center_distance,
                        dhash_distance, ahash_distance, exact_bytes,
                        status, updated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending', NOW())
                    ON CONFLICT (first_media_id, second_media_id) DO UPDATE
                    SET similarity_score = EXCLUDED.similarity_score,
                        phash_distance = EXCLUDED.phash_distance,
                        center_distance = EXCLUDED.center_distance,
                        dhash_distance = EXCLUDED.dhash_distance,
                        ahash_distance = EXCLUDED.ahash_distance,
                        exact_bytes = EXCLUDED.exact_bytes,
                        status = CASE
                            WHEN media_duplicate_candidates.status = 'confirmed'
                            THEN 'confirmed'
                            WHEN media_duplicate_candidates.status = 'ignored'
                            THEN 'ignored'
                            ELSE 'pending'
                        END,
                        updated_at = NOW()
                    """,
                    first_id,
                    second_id,
                    comparison.similarity_score,
                    comparison.phash_distance,
                    comparison.center_distance,
                    comparison.dhash_distance,
                    comparison.ahash_distance,
                    comparison.exact_bytes,
                )


async def scan_media_target(
    bot: Bot,
    database: Database,
    target: MediaScanTarget,
) -> None:
    try:
        destination = io.BytesIO()
        await bot.download(
            target.telegram_file_id,
            destination=destination,
            seek=True,
        )
        fingerprint = await asyncio.to_thread(
            build_visual_fingerprint,
            destination.getvalue(),
        )
        comparisons: list[tuple[int, FingerprintComparison]] = []
        for stored in await _load_other_fingerprints(database, target.media_id):
            comparison = compare_fingerprints(fingerprint, stored.fingerprint)
            if comparison.is_candidate:
                comparisons.append((stored.media_id, comparison))
        await _store_fingerprint_and_candidates(
            database,
            target.media_id,
            fingerprint,
            comparisons,
        )
        logger.info(
            "Visual fingerprint ready media_id=%s candidates=%s",
            target.media_id,
            len(comparisons),
        )
    except Exception as error:
        logger.exception("Visual fingerprint failed media_id=%s", target.media_id)
        async with database._require_pool().acquire() as connection:
            await connection.execute(
                """
                UPDATE media_files
                SET visual_scan_status = 'error',
                    visual_scan_error = $2,
                    visual_scanned_at = NOW()
                WHERE id = $1
                """,
                target.media_id,
                str(error)[:2000],
            )
            if isinstance(error, TelegramAPIError):
                await connection.execute(
                    """
                    INSERT INTO media_file_checks (
                        media_id, status, checked_at, error_text, updated_at
                    )
                    VALUES ($1, 'broken', NOW(), $2, NOW())
                    ON CONFLICT (media_id) DO UPDATE
                    SET status = 'broken', checked_at = NOW(),
                        error_text = EXCLUDED.error_text, updated_at = NOW()
                    """,
                    target.media_id,
                    str(error)[:2000],
                )


async def _claim_file_checks(
    database: Database,
    *,
    limit: int = 4,
) -> list[tuple[int, str]]:
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT mf.id, mf.telegram_file_id
            FROM media_files AS mf
            JOIN media_file_checks AS fc ON fc.media_id = mf.id
            WHERE fc.status = 'unknown'
            ORDER BY mf.id
            LIMIT $1
            """,
            max(1, min(limit, 10)),
        )
    return [(int(row["id"]), str(row["telegram_file_id"])) for row in rows]


async def verify_media_file(
    bot: Bot,
    database: Database,
    media_id: int,
    telegram_file_id: str,
) -> None:
    status = "ok"
    error_text: str | None = None
    try:
        await bot.get_file(telegram_file_id)
    except TelegramAPIError as error:
        status = "broken"
        error_text = str(error)[:2000]
    async with database._require_pool().acquire() as connection:
        await connection.execute(
            """
            INSERT INTO media_file_checks (media_id, status, checked_at, error_text, updated_at)
            VALUES ($1, $2, NOW(), $3, NOW())
            ON CONFLICT (media_id) DO UPDATE
            SET status = EXCLUDED.status,
                checked_at = NOW(),
                error_text = EXCLUDED.error_text,
                updated_at = NOW()
            """,
            media_id,
            status,
            error_text,
        )


async def run_media_quality_worker(
    bot: Bot,
    database: Database,
    *,
    interval_seconds: float = 4.0,
) -> None:
    while True:
        try:
            targets = await _claim_pending_images(database)
            for target in targets:
                await scan_media_target(bot, database, target)
            for media_id, file_id in await _claim_file_checks(database):
                await verify_media_file(bot, database, media_id, file_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Media quality worker failed")
        await asyncio.sleep(interval_seconds)


async def list_duplicate_candidates(
    database: Database,
    *,
    status: str = "pending",
    page: int = 0,
    page_size: int = 6,
) -> DuplicatePage:
    safe_size = max(1, min(page_size, 8))
    safe_page = max(0, page)
    async with database._require_pool().acquire() as connection:
        total = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM media_duplicate_candidates WHERE status = $1",
                status,
            )
            or 0
        )
        total_pages = max(1, (total + safe_size - 1) // safe_size)
        normalized_page = min(safe_page, total_pages - 1)
        rows = await connection.fetch(
            """
            SELECT
                dc.*,
                COALESCE(m1.original_file_name, m1.storage_file_name) AS first_file_name,
                COALESCE(m2.original_file_name, m2.storage_file_name) AS second_file_name,
                m1.telegram_file_id AS first_file_id,
                m2.telegram_file_id AS second_file_id,
                m1.media_type AS first_media_type,
                m2.media_type AS second_media_type,
                m1.mime_type AS first_mime_type,
                m2.mime_type AS second_mime_type,
                COALESCE((
                    SELECT ARRAY_AGG(c.name ORDER BY c.name)
                    FROM character_media cm JOIN characters c ON c.id = cm.character_id
                    WHERE cm.media_id = m1.id
                ), ARRAY[]::VARCHAR[]) AS first_characters,
                COALESCE((
                    SELECT ARRAY_AGG(c.name ORDER BY c.name)
                    FROM character_media cm JOIN characters c ON c.id = cm.character_id
                    WHERE cm.media_id = m2.id
                ), ARRAY[]::VARCHAR[]) AS second_characters
            FROM media_duplicate_candidates dc
            JOIN media_files m1 ON m1.id = dc.first_media_id
            JOIN media_files m2 ON m2.id = dc.second_media_id
            WHERE dc.status = $1
            ORDER BY dc.similarity_score DESC, dc.id
            OFFSET $2 LIMIT $3
            """,
            status,
            normalized_page * safe_size,
            safe_size,
        )
    return DuplicatePage(
        items=tuple(_row_to_duplicate(row) for row in rows),
        page=normalized_page,
        page_size=safe_size,
        total_items=total,
    )


def _row_to_duplicate(row) -> DuplicateCandidate:
    return DuplicateCandidate(
        id=int(row["id"]),
        first_media_id=int(row["first_media_id"]),
        second_media_id=int(row["second_media_id"]),
        similarity_score=int(row["similarity_score"]),
        phash_distance=int(row["phash_distance"]),
        center_distance=int(row["center_distance"]),
        dhash_distance=int(row["dhash_distance"]),
        ahash_distance=int(row["ahash_distance"]),
        exact_bytes=bool(row["exact_bytes"]),
        status=str(row["status"]),
        first_file_name=str(row["first_file_name"]),
        second_file_name=str(row["second_file_name"]),
        first_file_id=str(row["first_file_id"]),
        second_file_id=str(row["second_file_id"]),
        first_media_type=str(row["first_media_type"]),
        second_media_type=str(row["second_media_type"]),
        first_mime_type=row["first_mime_type"],
        second_mime_type=row["second_mime_type"],
        first_characters=tuple(str(value) for value in row["first_characters"]),
        second_characters=tuple(str(value) for value in row["second_characters"]),
    )


async def get_duplicate_candidate(
    database: Database,
    candidate_id: int,
) -> DuplicateCandidate | None:
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                dc.*,
                COALESCE(m1.original_file_name, m1.storage_file_name) AS first_file_name,
                COALESCE(m2.original_file_name, m2.storage_file_name) AS second_file_name,
                m1.telegram_file_id AS first_file_id,
                m2.telegram_file_id AS second_file_id,
                m1.media_type AS first_media_type,
                m2.media_type AS second_media_type,
                m1.mime_type AS first_mime_type,
                m2.mime_type AS second_mime_type,
                COALESCE((SELECT ARRAY_AGG(c.name ORDER BY c.name)
                    FROM character_media cm JOIN characters c ON c.id = cm.character_id
                    WHERE cm.media_id = m1.id), ARRAY[]::VARCHAR[]) AS first_characters,
                COALESCE((SELECT ARRAY_AGG(c.name ORDER BY c.name)
                    FROM character_media cm JOIN characters c ON c.id = cm.character_id
                    WHERE cm.media_id = m2.id), ARRAY[]::VARCHAR[]) AS second_characters
            FROM media_duplicate_candidates dc
            JOIN media_files m1 ON m1.id = dc.first_media_id
            JOIN media_files m2 ON m2.id = dc.second_media_id
            WHERE dc.id = $1
            """,
            candidate_id,
        )
    return _row_to_duplicate(row) if row is not None else None


async def decide_duplicate_candidate(
    database: Database,
    candidate_id: int,
    *,
    status: str,
    decided_by: int,
) -> bool:
    if status not in {"confirmed", "ignored", "pending"}:
        raise ValueError("Неизвестное решение по дублю.")
    async with database._require_pool().acquire() as connection:
        value = await connection.fetchval(
            """
            UPDATE media_duplicate_candidates
            SET status = $2,
                decided_by = CASE WHEN $2 = 'pending' THEN NULL ELSE $3 END,
                decided_at = CASE WHEN $2 = 'pending' THEN NULL ELSE NOW() END,
                updated_at = NOW()
            WHERE id = $1
            RETURNING id
            """,
            candidate_id,
            status,
            decided_by,
        )
    return value is not None


async def reset_failed_scans(database: Database) -> int:
    async with database._require_pool().acquire() as connection:
        result = await connection.execute(
            """
            UPDATE media_files
            SET visual_scan_status = 'pending', visual_scan_error = NULL
            WHERE visual_scan_status = 'error'
              AND (
                  media_type = 'photo'
                  OR (media_type = 'document' AND COALESCE(mime_type, '') LIKE 'image/%')
              )
            """
        )
    return int(result.split()[-1])

from __future__ import annotations

import asyncio
import io
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

import velvet_bot.analytics_review as analytics_review
import velvet_bot.media_quality as media_quality
from velvet_bot.database import Database
from velvet_bot.visual_fingerprint import build_visual_fingerprint, compare_fingerprints

logger = logging.getLogger(__name__)
_DOWNLOAD_LIMIT = 20 * 1024 * 1024
_INSTALLED = False


async def set_manual_publication_type(
    database: Database,
    *,
    token_id: int,
    post_type: str,
    changed_by: int | None,
):
    """Set a manual publication type without ambiguous PostgreSQL parameters."""
    if post_type not in analytics_review.POST_TYPE_LABELS:
        raise ValueError("Неизвестный тип публикации.")

    item = await analytics_review.get_publication_review(database, token_id=token_id)
    if item is None:
        raise ValueError("Публикация больше не найдена.")

    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            channel_id = int(
                await connection.fetchval(
                    "SELECT channel_id FROM analytics_review_items WHERE id = $1::BIGINT",
                    token_id,
                )
            )
            await analytics_review._record_classification_change(
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

    refreshed = await analytics_review.get_publication_review(
        database,
        token_id=token_id,
    )
    if refreshed is None:
        raise RuntimeError("Публикация исчезла после обновления.")
    return refreshed


async def decide_duplicate_candidate(
    database: Database,
    candidate_id: int,
    *,
    status: str,
    decided_by: int,
) -> bool:
    """Store a duplicate decision using one explicit SQL type per parameter."""
    if status not in {"confirmed", "ignored", "pending"}:
        raise ValueError("Неизвестное решение по дублю.")

    async with database._require_pool().acquire() as connection:
        value = await connection.fetchval(
            """
            UPDATE media_duplicate_candidates
            SET status = $2::VARCHAR,
                decided_by = CASE
                    WHEN $2::VARCHAR = 'pending'::VARCHAR THEN NULL::BIGINT
                    ELSE $3::BIGINT
                END,
                decided_at = CASE
                    WHEN $2::VARCHAR = 'pending'::VARCHAR THEN NULL::TIMESTAMPTZ
                    ELSE NOW()
                END,
                updated_at = NOW()
            WHERE id = $1::BIGINT
            RETURNING id
            """,
            candidate_id,
            status,
            decided_by,
        )
    return value is not None


async def claim_pending_images(
    database: Database,
    *,
    limit: int = 2,
) -> list[media_quality.MediaScanTarget]:
    """Prefer a stored Telegram preview for files above the Bot API limit."""
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            rows = await connection.fetch(
                """
                SELECT
                    id,
                    CASE
                        WHEN COALESCE(file_size, 0) > $2::BIGINT
                             AND preview_file_id IS NOT NULL
                        THEN preview_file_id
                        ELSE telegram_file_id
                    END AS scan_file_id,
                    COALESCE(original_file_name, storage_file_name) AS display_name
                FROM media_files
                WHERE visual_scan_status = 'pending'
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT $1::INTEGER
                """,
                max(1, min(limit, 5)),
                _DOWNLOAD_LIMIT,
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
        media_quality.MediaScanTarget(
            media_id=int(row["id"]),
            telegram_file_id=str(row["scan_file_id"]),
            display_name=str(row["display_name"]),
        )
        for row in rows
    ]


async def _mark_scan_error(
    database: Database,
    *,
    media_id: int,
    error: Exception,
    broken_file: bool,
) -> None:
    error_text = str(error)[:2000]
    async with database._require_pool().acquire() as connection:
        await connection.execute(
            """
            UPDATE media_files
            SET visual_scan_status = 'error',
                visual_scan_error = $2::TEXT,
                visual_scanned_at = NOW()
            WHERE id = $1::BIGINT
            """,
            media_id,
            error_text,
        )
        if broken_file:
            await connection.execute(
                """
                INSERT INTO media_file_checks (
                    media_id, status, checked_at, error_text, updated_at
                )
                VALUES ($1::BIGINT, 'broken', NOW(), $2::TEXT, NOW())
                ON CONFLICT (media_id) DO UPDATE
                SET status = 'broken',
                    checked_at = NOW(),
                    error_text = EXCLUDED.error_text,
                    updated_at = NOW()
                """,
                media_id,
                error_text,
            )


async def scan_media_target(
    bot: Bot,
    database: Database,
    target: media_quality.MediaScanTarget,
) -> None:
    """Build a fingerprint while treating an oversized file as unsupported, not broken."""
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
        comparisons = []
        for stored in await media_quality._load_other_fingerprints(
            database,
            target.media_id,
        ):
            comparison = compare_fingerprints(fingerprint, stored.fingerprint)
            if comparison.is_candidate:
                comparisons.append((stored.media_id, comparison))
        await media_quality._store_fingerprint_and_candidates(
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
    except TelegramBadRequest as error:
        if "file is too big" in str(error).casefold():
            logger.info(
                "Visual fingerprint skipped media_id=%s: file exceeds Bot API download limit",
                target.media_id,
            )
            await _mark_scan_error(
                database,
                media_id=target.media_id,
                error=RuntimeError(
                    "Пропущено: файл превышает лимит скачивания Telegram Bot API, "
                    "а сохранённое превью отсутствует."
                ),
                broken_file=False,
            )
            return
        logger.warning(
            "Visual fingerprint Telegram error media_id=%s: %s",
            target.media_id,
            error,
        )
        await _mark_scan_error(
            database,
            media_id=target.media_id,
            error=error,
            broken_file=True,
        )
    except TelegramAPIError as error:
        logger.warning(
            "Visual fingerprint Telegram error media_id=%s: %s",
            target.media_id,
            error,
        )
        await _mark_scan_error(
            database,
            media_id=target.media_id,
            error=error,
            broken_file=True,
        )
    except Exception as error:
        logger.exception("Visual fingerprint failed media_id=%s", target.media_id)
        await _mark_scan_error(
            database,
            media_id=target.media_id,
            error=error,
            broken_file=False,
        )


class _ArchiveDeleteNoiseFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.getMessage() == "Could not delete archive topic message":
            record.levelno = logging.INFO
            record.levelname = "INFO"
            record.msg = "Archive topic message was already absent or cannot be deleted"
            record.args = ()
        return True


def install_runtime_log_hotfixes() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    analytics_review.set_manual_publication_type = set_manual_publication_type
    media_quality.decide_duplicate_candidate = decide_duplicate_candidate
    media_quality._claim_pending_images = claim_pending_images
    media_quality.scan_media_target = scan_media_target

    public_manager_logger = logging.getLogger("velvet_bot.handlers.public_manager")
    public_manager_logger.addFilter(_ArchiveDeleteNoiseFilter())
    _INSTALLED = True

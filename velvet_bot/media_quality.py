from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from velvet_bot.database import Database
from velvet_bot.domains.media_quality import (
    DuplicateCandidate,
    DuplicatePage,
    MediaQualityRepository,
    MediaQualityService,
    MediaScanTarget,
    StoredFingerprint,
)
from velvet_bot.visual_fingerprint import FingerprintComparison, VisualFingerprint

logger = logging.getLogger(__name__)


async def _claim_pending_images(
    database: Database,
    *,
    limit: int = 2,
) -> list[MediaScanTarget]:
    return await MediaQualityRepository(database).claim_pending_images(limit=limit)


async def _load_other_fingerprints(
    database: Database,
    media_id: int,
) -> list[StoredFingerprint]:
    return await MediaQualityRepository(database).load_other_fingerprints(media_id)


async def _store_fingerprint_and_candidates(
    database: Database,
    media_id: int,
    fingerprint: VisualFingerprint,
    comparisons: list[tuple[int, FingerprintComparison]],
) -> None:
    await MediaQualityRepository(database).store_fingerprint_and_candidates(
        media_id,
        fingerprint,
        comparisons,
    )


async def scan_media_target(
    bot: Bot,
    database: Database,
    target: MediaScanTarget,
) -> None:
    service = MediaQualityService(
        bot=bot,
        repository=MediaQualityRepository(database),
    )
    await service.scan_target(target)


async def _claim_file_checks(
    database: Database,
    *,
    limit: int = 4,
) -> list[tuple[int, str]]:
    targets = await MediaQualityRepository(database).claim_file_checks(limit=limit)
    return [(target.media_id, target.telegram_file_id) for target in targets]


async def verify_media_file(
    bot: Bot,
    database: Database,
    media_id: int,
    telegram_file_id: str,
) -> None:
    service = MediaQualityService(
        bot=bot,
        repository=MediaQualityRepository(database),
    )
    await service.verify_file(
        media_id=media_id,
        telegram_file_id=telegram_file_id,
    )


async def run_media_quality_worker(
    bot: Bot,
    database: Database,
    *,
    interval_seconds: float = 4.0,
) -> None:
    """Backward-compatible standalone loop around the domain service."""
    service = MediaQualityService(
        bot=bot,
        repository=MediaQualityRepository(database),
    )
    while True:
        try:
            await service.process_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # p2-approved-boundary: isolate-media-quality-worker-iteration
            logger.exception("Media quality worker failed")
        await asyncio.sleep(interval_seconds)


async def list_duplicate_candidates(
    database: Database,
    *,
    status: str = "pending",
    page: int = 0,
    page_size: int = 6,
) -> DuplicatePage:
    return await MediaQualityRepository(database).list_duplicate_candidates(
        status=status,
        page=page,
        page_size=page_size,
    )


async def get_duplicate_candidate(
    database: Database,
    candidate_id: int,
) -> DuplicateCandidate | None:
    return await MediaQualityRepository(database).get_duplicate_candidate(candidate_id)


async def decide_duplicate_candidate(
    database: Database,
    candidate_id: int,
    *,
    status: str,
    decided_by: int,
) -> bool:
    return await MediaQualityRepository(database).decide_duplicate_candidate(
        candidate_id,
        status=status,
        decided_by=decided_by,
    )


async def reset_failed_scans(database: Database) -> int:
    return await MediaQualityRepository(database).reset_failed_scans()


__all__ = (
    "DuplicateCandidate",
    "DuplicatePage",
    "MediaScanTarget",
    "StoredFingerprint",
    "decide_duplicate_candidate",
    "get_duplicate_candidate",
    "list_duplicate_candidates",
    "reset_failed_scans",
    "run_media_quality_worker",
    "scan_media_target",
    "verify_media_file",
)

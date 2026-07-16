from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.media_quality.models import (
    MediaFileCheckTarget,
    MediaScanTarget,
    StoredFingerprint,
)
from velvet_bot.visual_fingerprint import FingerprintComparison, VisualFingerprint

TELEGRAM_BOT_DOWNLOAD_LIMIT = 20 * 1024 * 1024


class MediaQualityRepository:
    """Own all PostgreSQL operations used by the media-quality worker."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def claim_pending_images(self, *, limit: int = 2) -> list[MediaScanTarget]:
        safe_limit = max(1, min(limit, 5))
        async with self._database._require_pool().acquire() as connection:
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
                    safe_limit,
                    TELEGRAM_BOT_DOWNLOAD_LIMIT,
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
                telegram_file_id=str(row["scan_file_id"]),
                display_name=str(row["display_name"]),
            )
            for row in rows
        ]

    async def load_other_fingerprints(self, media_id: int) -> list[StoredFingerprint]:
        async with self._database._require_pool().acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT media_id, fingerprint_version, content_sha256,
                       phash, center_phash, dhash, ahash,
                       width, height, image_format
                FROM media_visual_fingerprints
                WHERE media_id <> $1::BIGINT
                """,
                media_id,
            )
        return [self._row_to_fingerprint(row) for row in rows]

    async def store_fingerprint_and_candidates(
        self,
        media_id: int,
        fingerprint: VisualFingerprint,
        comparisons: list[tuple[int, FingerprintComparison]],
    ) -> None:
        async with self._database._require_pool().acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO media_visual_fingerprints (
                        media_id, fingerprint_version, content_sha256,
                        phash, center_phash, dhash, ahash,
                        width, height, image_format, updated_at
                    )
                    VALUES (
                        $1::BIGINT, $2::INTEGER, $3::TEXT, $4::TEXT, $5::TEXT,
                        $6::TEXT, $7::TEXT, $8::INTEGER, $9::INTEGER, $10::TEXT, NOW()
                    )
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
                    WHERE id = $1::BIGINT
                    """,
                    media_id,
                )
                await self._record_file_check_on_connection(
                    connection,
                    media_id=media_id,
                    status="ok",
                    error_text=None,
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
                        VALUES (
                            $1::BIGINT, $2::BIGINT, $3::INTEGER, $4::INTEGER,
                            $5::INTEGER, $6::INTEGER, $7::INTEGER, $8::BOOLEAN,
                            'pending', NOW()
                        )
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

    async def mark_scan_error(
        self,
        *,
        media_id: int,
        error: Exception,
        broken_file: bool,
    ) -> None:
        error_text = str(error)[:2000]
        async with self._database._require_pool().acquire() as connection:
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
                await self._record_file_check_on_connection(
                    connection,
                    media_id=media_id,
                    status="broken",
                    error_text=error_text,
                )

    async def claim_file_checks(self, *, limit: int = 4) -> list[MediaFileCheckTarget]:
        safe_limit = max(1, min(limit, 10))
        async with self._database._require_pool().acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT mf.id, mf.telegram_file_id
                FROM media_files AS mf
                JOIN media_file_checks AS fc ON fc.media_id = mf.id
                WHERE fc.status = 'unknown'
                ORDER BY mf.id
                LIMIT $1::INTEGER
                """,
                safe_limit,
            )
        return [
            MediaFileCheckTarget(
                media_id=int(row["id"]),
                telegram_file_id=str(row["telegram_file_id"]),
            )
            for row in rows
        ]

    async def record_file_check(
        self,
        *,
        media_id: int,
        status: str,
        error_text: str | None,
    ) -> None:
        async with self._database._require_pool().acquire() as connection:
            await self._record_file_check_on_connection(
                connection,
                media_id=media_id,
                status=status,
                error_text=error_text,
            )

    @staticmethod
    async def _record_file_check_on_connection(
        connection,
        *,
        media_id: int,
        status: str,
        error_text: str | None,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO media_file_checks (
                media_id, status, checked_at, error_text, updated_at
            )
            VALUES ($1::BIGINT, $2::VARCHAR, NOW(), $3::TEXT, NOW())
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

    @staticmethod
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


__all__ = ("MediaQualityRepository", "TELEGRAM_BOT_DOWNLOAD_LIMIT")

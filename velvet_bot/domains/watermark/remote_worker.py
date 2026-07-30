from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from velvet_bot.database import Database


@dataclass(frozen=True, slots=True)
class KritaRemoteLease:
    job_id: int
    revision: int
    worker_id: str
    token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class KritaWorkerSnapshot:
    worker_id: str
    version: str | None
    hostname: str | None
    last_seen_at: datetime
    active_job_id: int | None
    active_revision: int | None


def hash_lease_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class KritaRemoteRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def heartbeat_worker(
        self,
        *,
        worker_id: str,
        version: str | None,
        hostname: str | None,
        active_job_id: int | None = None,
        active_revision: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO krita_remote_workers (
                    worker_id, version, hostname, last_seen_at,
                    active_job_id, active_revision, metadata
                )
                VALUES ($1, $2, $3, NOW(), $4, $5, $6::jsonb)
                ON CONFLICT (worker_id) DO UPDATE
                SET version = EXCLUDED.version,
                    hostname = EXCLUDED.hostname,
                    last_seen_at = NOW(),
                    active_job_id = EXCLUDED.active_job_id,
                    active_revision = EXCLUDED.active_revision,
                    metadata = EXCLUDED.metadata
                """,
                worker_id,
                version,
                hostname,
                active_job_id,
                active_revision,
                json.dumps(metadata or {}, ensure_ascii=False),
            )

    async def claim(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> KritaRemoteLease | None:
        token = secrets.token_urlsafe(32)
        token_hash = hash_lease_token(token)
        async with self._database.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT r.job_id, r.revision
                    FROM watermark_revisions AS r
                    JOIN watermark_jobs AS j ON j.id = r.job_id
                    WHERE r.status = 'pending'
                      AND j.status = 'active'
                      AND r.revision = j.current_revision
                    ORDER BY r.created_at, r.job_id, r.revision
                    FOR UPDATE OF r SKIP LOCKED
                    LIMIT 1
                    """
                )
                if row is None:
                    return None
                updated = await connection.fetchrow(
                    """
                    UPDATE watermark_revisions
                    SET status = 'processing',
                        error = NULL,
                        remote_worker_id = $3,
                        remote_lease_token_hash = $4,
                        remote_lease_expires_at = NOW() + ($5 * INTERVAL '1 second'),
                        remote_heartbeat_at = NOW()
                    WHERE job_id = $1
                      AND revision = $2
                      AND status = 'pending'
                    RETURNING remote_lease_expires_at
                    """,
                    int(row["job_id"]),
                    int(row["revision"]),
                    worker_id,
                    token_hash,
                    max(30, int(lease_seconds)),
                )
                if updated is None:
                    return None
        expires_at = updated["remote_lease_expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return KritaRemoteLease(
            job_id=int(row["job_id"]),
            revision=int(row["revision"]),
            worker_id=worker_id,
            token=token,
            expires_at=expires_at,
        )

    async def validate_lease(
        self,
        *,
        job_id: int,
        revision: int,
        worker_id: str,
        token: str,
    ) -> bool:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM watermark_revisions
                    WHERE job_id = $1
                      AND revision = $2
                      AND status = 'processing'
                      AND remote_worker_id = $3
                      AND remote_lease_token_hash = $4
                      AND remote_lease_expires_at > NOW()
                )
                """,
                int(job_id),
                int(revision),
                worker_id,
                hash_lease_token(token),
            )
        return bool(value)

    async def heartbeat_lease(
        self,
        *,
        job_id: int,
        revision: int,
        worker_id: str,
        token: str,
        lease_seconds: int,
    ) -> datetime | None:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                UPDATE watermark_revisions
                SET remote_heartbeat_at = NOW(),
                    remote_lease_expires_at = NOW() + ($5 * INTERVAL '1 second')
                WHERE job_id = $1
                  AND revision = $2
                  AND status = 'processing'
                  AND remote_worker_id = $3
                  AND remote_lease_token_hash = $4
                  AND remote_lease_expires_at > NOW()
                RETURNING remote_lease_expires_at
                """,
                int(job_id),
                int(revision),
                worker_id,
                hash_lease_token(token),
                max(30, int(lease_seconds)),
            )
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value

    async def fail(
        self,
        *,
        job_id: int,
        revision: int,
        worker_id: str,
        token: str,
        error: str,
    ) -> bool:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE watermark_revisions
                SET status = 'error',
                    error = $5,
                    completed_at = NOW(),
                    remote_worker_id = NULL,
                    remote_lease_token_hash = NULL,
                    remote_lease_expires_at = NULL,
                    remote_heartbeat_at = NULL
                WHERE job_id = $1
                  AND revision = $2
                  AND status = 'processing'
                  AND remote_worker_id = $3
                  AND remote_lease_token_hash = $4
                  AND remote_lease_expires_at > NOW()
                """,
                int(job_id),
                int(revision),
                worker_id,
                hash_lease_token(token),
                error[:2000],
            )
        return result.endswith("1")

    async def requeue_expired(self, *, limit: int = 100) -> int:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                WITH expired AS (
                    SELECT job_id, revision
                    FROM watermark_revisions
                    WHERE status = 'processing'
                      AND remote_worker_id IS NOT NULL
                      AND remote_lease_expires_at <= NOW()
                    ORDER BY remote_lease_expires_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT $1
                )
                UPDATE watermark_revisions AS r
                SET status = 'pending',
                    request_path = NULL,
                    output_path = NULL,
                    response_path = NULL,
                    error = 'Удалённый Krita worker потерял lease; задача возвращена в очередь.',
                    remote_worker_id = NULL,
                    remote_lease_token_hash = NULL,
                    remote_lease_expires_at = NULL,
                    remote_heartbeat_at = NULL
                FROM expired
                WHERE r.job_id = expired.job_id
                  AND r.revision = expired.revision
                RETURNING r.job_id
                """,
                max(1, min(int(limit), 500)),
            )
        return len(rows)

    async def clear_worker_activity(self, *, worker_id: str) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE krita_remote_workers
                SET active_job_id = NULL,
                    active_revision = NULL,
                    last_seen_at = NOW()
                WHERE worker_id = $1
                """,
                worker_id,
            )


__all__ = (
    "KritaRemoteLease",
    "KritaRemoteRepository",
    "KritaWorkerSnapshot",
    "hash_lease_token",
)

from __future__ import annotations

from dataclasses import replace
from typing import Any, Literal

from velvet_bot.database import Database
from velvet_bot.domains.watermark.models import (
    WatermarkJob,
    WatermarkRevision,
    WatermarkSettings,
    WatermarkWorkItem,
)

CancelResult = Literal["cancelled", "already_cancelled", "approved"]


class WatermarkRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def create_job(
        self,
        *,
        owner_user_id: int,
        chat_id: int,
        source_message_id: int,
        source_file_id: str,
        source_file_unique_id: str | None,
        source_path: str,
        settings: WatermarkSettings,
    ) -> WatermarkWorkItem:
        settings = settings.normalized()
        async with self._database.acquire() as connection:
            async with connection.transaction():
                job_row = await connection.fetchrow(
                    """
                    INSERT INTO watermark_jobs (
                        owner_user_id, chat_id, source_message_id,
                        source_file_id, source_file_unique_id, source_path
                    )
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING *
                    """,
                    owner_user_id,
                    chat_id,
                    source_message_id,
                    source_file_id,
                    source_file_unique_id,
                    source_path,
                )
                if job_row is None:
                    raise RuntimeError("Не удалось создать задание водяного знака.")
                revision_row = await self._insert_revision(
                    connection,
                    job_id=int(job_row["id"]),
                    revision=1,
                    settings=settings,
                )
        return WatermarkWorkItem(
            job=self._map_job(job_row),
            revision=self._map_revision(revision_row),
        )

    async def get_current(self, job_id: int) -> WatermarkWorkItem | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(self._current_query(), job_id)
        return self._map_work_item(row) if row is not None else None

    async def create_revision(
        self,
        job_id: int,
        *,
        settings: WatermarkSettings,
    ) -> WatermarkWorkItem:
        settings = settings.normalized()
        async with self._database.acquire() as connection:
            async with connection.transaction():
                job_row = await connection.fetchrow(
                    "SELECT * FROM watermark_jobs WHERE id = $1 FOR UPDATE",
                    job_id,
                )
                if job_row is None:
                    raise ValueError("Задание водяного знака не найдено.")
                if str(job_row["status"]) in {"approved", "cancelled"}:
                    raise ValueError("Задание уже завершено.")
                revision = int(job_row["current_revision"]) + 1
                revision_row = await self._insert_revision(
                    connection,
                    job_id=job_id,
                    revision=revision,
                    settings=settings,
                )
                job_row = await connection.fetchrow(
                    """
                    UPDATE watermark_jobs
                    SET current_revision = $2,
                        status = 'active',
                        updated_at = NOW()
                    WHERE id = $1
                    RETURNING *
                    """,
                    job_id,
                    revision,
                )
        if job_row is None:
            raise RuntimeError("Не удалось обновить задание водяного знака.")
        return WatermarkWorkItem(
            job=self._map_job(job_row),
            revision=self._map_revision(revision_row),
        )

    async def undo(self, job_id: int) -> WatermarkWorkItem:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT r.*
                FROM watermark_jobs AS j
                JOIN watermark_revisions AS r ON r.job_id = j.id
                WHERE j.id = $1 AND r.revision < j.current_revision
                ORDER BY r.revision DESC
                LIMIT 1
                """,
                job_id,
            )
        if row is None:
            raise ValueError("Предыдущей версии настроек нет.")
        return await self.create_revision(job_id, settings=self._settings_from_row(row))

    async def set_control_message(self, job_id: int, message_id: int) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE watermark_jobs
                SET control_message_id = $2, updated_at = NOW()
                WHERE id = $1
                """,
                job_id,
                message_id,
            )

    async def set_preview_message(self, job_id: int, message_id: int) -> int | None:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                previous = await connection.fetchval(
                    "SELECT preview_message_id FROM watermark_jobs WHERE id = $1 FOR UPDATE",
                    job_id,
                )
                await connection.execute(
                    """
                    UPDATE watermark_jobs
                    SET preview_message_id = $2, updated_at = NOW()
                    WHERE id = $1
                    """,
                    job_id,
                    message_id,
                )
        return int(previous) if previous is not None else None

    async def claim_pending(self) -> WatermarkWorkItem | None:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    self._joined_query(
                        """
                        WHERE r.status = 'pending'
                          AND j.status = 'active'
                          AND r.revision = j.current_revision
                        ORDER BY r.created_at, r.job_id, r.revision
                        FOR UPDATE OF r SKIP LOCKED
                        LIMIT 1
                        """
                    )
                )
                if row is None:
                    return None
                await connection.execute(
                    """
                    UPDATE watermark_revisions
                    SET status = 'processing', error = NULL
                    WHERE job_id = $1 AND revision = $2 AND status = 'pending'
                    """,
                    int(row["id"]),
                    int(row["r_revision"]),
                )
        item = self._map_work_item(row)
        return WatermarkWorkItem(
            job=item.job,
            revision=replace(item.revision, status="processing", error=None),
        )

    async def set_dispatched_paths(
        self,
        *,
        job_id: int,
        revision: int,
        request_path: str,
        output_path: str,
        response_path: str,
    ) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE watermark_revisions
                SET request_path = $3,
                    output_path = $4,
                    response_path = $5
                WHERE job_id = $1 AND revision = $2 AND status = 'processing'
                """,
                job_id,
                revision,
                request_path,
                output_path,
                response_path,
            )

    async def list_processing(self, *, limit: int = 20) -> list[WatermarkWorkItem]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                self._joined_query(
                    """
                    WHERE r.status = 'processing'
                    ORDER BY r.created_at
                    LIMIT $1
                    """
                ),
                max(1, min(limit, 100)),
            )
        return [self._map_work_item(row) for row in rows]

    async def mark_ready(
        self,
        *,
        job_id: int,
        revision: int,
        telegram_preview_file_id: str | None,
    ) -> bool:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                result = await connection.execute(
                    """
                    UPDATE watermark_revisions
                    SET status = 'ready',
                        telegram_preview_file_id = $3,
                        error = NULL,
                        completed_at = NOW()
                    WHERE job_id = $1
                      AND revision = $2
                      AND status = 'processing'
                    """,
                    job_id,
                    revision,
                    telegram_preview_file_id,
                )
                current = await connection.fetchval(
                    "SELECT current_revision FROM watermark_jobs WHERE id = $1",
                    job_id,
                )
        updated = result.endswith("1")
        return updated and current is not None and int(current) == revision

    async def mark_error(self, *, job_id: int, revision: int, error: str) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE watermark_revisions
                SET status = 'error', error = $3, completed_at = NOW()
                WHERE job_id = $1
                  AND revision = $2
                  AND status IN ('pending', 'processing')
                """,
                job_id,
                revision,
                error[:2000],
            )

    async def approve(self, job_id: int) -> WatermarkWorkItem:
        """Atomically approve the current ready revision and only that revision."""
        async with self._database.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    self._current_query(for_update=True),
                    job_id,
                )
                if row is None:
                    raise ValueError("Задание водяного знака не найдено.")
                status = str(row["status"])
                if status == "approved":
                    raise ValueError("Финальный файл уже подтверждён.")
                if status == "cancelled":
                    raise ValueError("Отменённое задание нельзя подтвердить.")
                if str(row["r_status"]) != "ready" or not row["r_output_path"]:
                    raise ValueError("Текущая версия ещё не готова.")

                final_path = str(row["r_output_path"])
                job_row = await connection.fetchrow(
                    """
                    UPDATE watermark_jobs
                    SET status = 'approved', final_path = $2, updated_at = NOW()
                    WHERE id = $1 AND status = 'active'
                    RETURNING *
                    """,
                    job_id,
                    final_path,
                )
                if job_row is None:
                    raise ValueError("Состояние задания изменилось; обновите карточку.")

        revision = self._map_revision_from_joined(row)
        return WatermarkWorkItem(job=self._map_job(job_row), revision=revision)

    async def cancel(self, job_id: int) -> CancelResult:
        """Cancel only active work; approved jobs are immutable."""
        async with self._database.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    "SELECT status FROM watermark_jobs WHERE id = $1 FOR UPDATE",
                    job_id,
                )
                if row is None:
                    raise ValueError("Задание водяного знака не найдено.")
                status = str(row["status"])
                if status == "approved":
                    return "approved"
                if status == "cancelled":
                    return "already_cancelled"
                await connection.execute(
                    """
                    UPDATE watermark_jobs
                    SET status = 'cancelled', updated_at = NOW()
                    WHERE id = $1 AND status = 'active'
                    """,
                    job_id,
                )
        return "cancelled"

    async def _insert_revision(
        self,
        connection,
        *,
        job_id: int,
        revision: int,
        settings: WatermarkSettings,
    ):
        row = await connection.fetchrow(
            """
            INSERT INTO watermark_revisions (
                job_id, revision, enabled, position, color,
                opacity, size, margin, lock_layer
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
            """,
            job_id,
            revision,
            settings.enabled,
            settings.position,
            settings.color,
            settings.opacity,
            settings.size,
            settings.margin,
            settings.lock,
        )
        if row is None:
            raise RuntimeError("Не удалось создать revision водяного знака.")
        return row

    @staticmethod
    def _joined_query(suffix: str) -> str:
        return """
            SELECT
                j.*,
                r.revision AS r_revision,
                r.enabled AS r_enabled,
                r.position AS r_position,
                r.color AS r_color,
                r.opacity AS r_opacity,
                r.size AS r_size,
                r.margin AS r_margin,
                r.lock_layer AS r_lock_layer,
                r.status AS r_status,
                r.request_path AS r_request_path,
                r.output_path AS r_output_path,
                r.response_path AS r_response_path,
                r.telegram_preview_file_id AS r_telegram_preview_file_id,
                r.error AS r_error,
                r.created_at AS r_created_at,
                r.completed_at AS r_completed_at
            FROM watermark_revisions AS r
            JOIN watermark_jobs AS j ON j.id = r.job_id
        """ + suffix

    @classmethod
    def _current_query(cls, *, for_update: bool = False) -> str:
        suffix = " WHERE j.id = $1 AND r.revision = j.current_revision"
        if for_update:
            suffix += " FOR UPDATE OF j, r"
        return cls._joined_query(suffix)

    @staticmethod
    def _map_job(row: Any) -> WatermarkJob:
        return WatermarkJob(
            id=int(row["id"]),
            owner_user_id=int(row["owner_user_id"]),
            chat_id=int(row["chat_id"]),
            source_message_id=int(row["source_message_id"]),
            source_file_id=str(row["source_file_id"]),
            source_file_unique_id=(
                str(row["source_file_unique_id"])
                if row["source_file_unique_id"] is not None
                else None
            ),
            source_path=str(row["source_path"]),
            status=str(row["status"]),
            current_revision=int(row["current_revision"]),
            control_message_id=(
                int(row["control_message_id"])
                if row["control_message_id"] is not None
                else None
            ),
            preview_message_id=(
                int(row["preview_message_id"])
                if row["preview_message_id"] is not None
                else None
            ),
            final_path=str(row["final_path"]) if row["final_path"] is not None else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @classmethod
    def _map_revision(cls, row: Any) -> WatermarkRevision:
        return WatermarkRevision(
            job_id=int(row["job_id"]),
            revision=int(row["revision"]),
            settings=cls._settings_from_row(row),
            status=str(row["status"]),
            request_path=str(row["request_path"]) if row["request_path"] is not None else None,
            output_path=str(row["output_path"]) if row["output_path"] is not None else None,
            response_path=str(row["response_path"]) if row["response_path"] is not None else None,
            telegram_preview_file_id=(
                str(row["telegram_preview_file_id"])
                if row["telegram_preview_file_id"] is not None
                else None
            ),
            error=str(row["error"]) if row["error"] is not None else None,
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )

    @classmethod
    def _map_revision_from_joined(cls, row: Any) -> WatermarkRevision:
        revision_row = {
            "job_id": row["id"],
            "revision": row["r_revision"],
            "enabled": row["r_enabled"],
            "position": row["r_position"],
            "color": row["r_color"],
            "opacity": row["r_opacity"],
            "size": row["r_size"],
            "margin": row["r_margin"],
            "lock_layer": row["r_lock_layer"],
            "status": row["r_status"],
            "request_path": row["r_request_path"],
            "output_path": row["r_output_path"],
            "response_path": row["r_response_path"],
            "telegram_preview_file_id": row["r_telegram_preview_file_id"],
            "error": row["r_error"],
            "created_at": row["r_created_at"],
            "completed_at": row["r_completed_at"],
        }
        return cls._map_revision(revision_row)

    @classmethod
    def _map_work_item(cls, row: Any) -> WatermarkWorkItem:
        return WatermarkWorkItem(
            job=cls._map_job(row),
            revision=cls._map_revision_from_joined(row),
        )

    @staticmethod
    def _settings_from_row(row: Any) -> WatermarkSettings:
        return WatermarkSettings(
            enabled=bool(row["enabled"]),
            position=str(row["position"]),
            color=str(row["color"]),
            opacity=int(row["opacity"]),
            size=float(row["size"]),
            margin=float(row["margin"]),
            lock=bool(row["lock_layer"]),
        ).normalized()


__all__ = ("CancelResult", "WatermarkRepository")

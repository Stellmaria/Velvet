from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID

from velvet_bot.database import Database
from velvet_bot.domains.ai_usage.task_models import AITaskStatus
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID

from .models import (
    AufCancellationResult,
    AufProvider,
    AufProviderSnapshot,
    AufRuntimeSettings,
    WorkspaceAufSettings,
)


class AufRuntimeRepository:
    """Persistence for Auf runtime settings.

    SQL table and module-key names retain ``meow`` only as a migration contract for
    already deployed databases. Python code uses the canonical Auf vocabulary.
    """

    def __init__(self, database: Database) -> None:
        self._database = database

    async def runtime_settings(self) -> AufRuntimeSettings:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT kie_concurrency_limit, grs_concurrency_limit,
                       workspace_default_limit, workspace_max_limit,
                       configured, setup_notice_sent_at, updated_by_user_id, updated_at
                FROM meow_runtime_settings
                WHERE singleton_id = 1
                """
            )
        if row is None:
            raise RuntimeError("Настройки параллельности Ауф не инициализированы.")
        return _runtime_from_row(row)

    async def set_provider_limit(
        self,
        *,
        provider: AufProvider,
        limit: int,
        updated_by_user_id: int,
    ) -> AufRuntimeSettings:
        field = (
            "kie_concurrency_limit"
            if provider is AufProvider.KIE
            else "grs_concurrency_limit"
        )
        safe_limit = max(1, min(100, int(limit)))
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                UPDATE meow_runtime_settings
                SET {field} = $1::INTEGER,
                    configured = TRUE,
                    updated_by_user_id = $2::BIGINT,
                    updated_at = NOW()
                WHERE singleton_id = 1
                RETURNING kie_concurrency_limit, grs_concurrency_limit,
                          workspace_default_limit, workspace_max_limit,
                          configured, setup_notice_sent_at,
                          updated_by_user_id, updated_at
                """,
                safe_limit,
                int(updated_by_user_id),
            )
        if row is None:
            raise RuntimeError("Не удалось обновить лимит провайдера.")
        return _runtime_from_row(row)

    async def confirm_runtime_settings(
        self,
        *,
        updated_by_user_id: int,
    ) -> AufRuntimeSettings:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE meow_runtime_settings
                SET configured = TRUE,
                    updated_by_user_id = $1::BIGINT,
                    updated_at = NOW()
                WHERE singleton_id = 1
                RETURNING kie_concurrency_limit, grs_concurrency_limit,
                          workspace_default_limit, workspace_max_limit,
                          configured, setup_notice_sent_at,
                          updated_by_user_id, updated_at
                """,
                int(updated_by_user_id),
            )
        if row is None:
            raise RuntimeError("Не удалось подтвердить настройки Ауф.")
        return _runtime_from_row(row)

    async def claim_setup_notice(self) -> bool:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE meow_runtime_settings
                SET setup_notice_sent_at = NOW(),
                    updated_at = NOW()
                WHERE singleton_id = 1
                  AND configured = FALSE
                  AND setup_notice_sent_at IS NULL
                """
            )
        return result.endswith(" 1")

    async def workspace_settings(self, workspace_id: int) -> WorkspaceAufSettings:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO workspace_auf_settings (workspace_id, concurrency_limit)
                SELECT $1::BIGINT, runtime.workspace_default_limit
                FROM meow_runtime_settings AS runtime
                WHERE runtime.singleton_id = 1
                ON CONFLICT (workspace_id) DO UPDATE
                SET workspace_id = EXCLUDED.workspace_id
                RETURNING workspace_id, concurrency_limit,
                          updated_by_user_id, updated_at
                """,
                int(workspace_id),
            )
        if row is None:
            raise RuntimeError("Не удалось загрузить настройки Ауф пространства.")
        return _workspace_from_row(row)

    async def set_workspace_limit(
        self,
        *,
        workspace_id: int,
        limit: int,
        updated_by_user_id: int,
    ) -> WorkspaceAufSettings:
        runtime = await self.runtime_settings()
        safe_limit = max(1, min(runtime.workspace_max_limit, int(limit)))
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO workspace_auf_settings (
                    workspace_id, concurrency_limit, updated_by_user_id
                )
                VALUES ($1::BIGINT, $2::INTEGER, $3::BIGINT)
                ON CONFLICT (workspace_id) DO UPDATE
                SET concurrency_limit = EXCLUDED.concurrency_limit,
                    updated_by_user_id = EXCLUDED.updated_by_user_id,
                    updated_at = NOW()
                RETURNING workspace_id, concurrency_limit,
                          updated_by_user_id, updated_at
                """,
                int(workspace_id),
                safe_limit,
                int(updated_by_user_id),
            )
        if row is None:
            raise RuntimeError("Не удалось обновить лимит пространства.")
        return _workspace_from_row(row)

    async def can_use_auf(
        self,
        *,
        workspace_id: int,
        user_id: int,
        global_owner: bool,
    ) -> bool:
        if global_owner or int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID:
            return True
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT TRUE
                FROM workspace_members AS member
                JOIN workspace_modules AS module
                  ON module.workspace_id = member.workspace_id
                 AND module.module_key = 'meow'
                WHERE member.workspace_id = $1::BIGINT
                  AND member.user_id = $2::BIGINT
                  AND member.role = 'owner'
                  AND module.is_allowed
                  AND module.is_enabled
                """,
                int(workspace_id),
                int(user_id),
            )
        return bool(value)

    async def is_workspace_owner(
        self,
        *,
        workspace_id: int,
        user_id: int,
    ) -> bool:
        if int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID:
            return True
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT TRUE
                FROM workspace_members
                WHERE workspace_id = $1::BIGINT
                  AND user_id = $2::BIGINT
                  AND role = 'owner'
                """,
                int(workspace_id),
                int(user_id),
            )
        return bool(value)

    async def hidden_modules_for_user(
        self,
        *,
        workspace_id: int,
        user_id: int,
    ) -> frozenset[str]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT module_key
                FROM workspace_user_module_preferences
                WHERE workspace_id = $1::BIGINT
                  AND user_id = $2::BIGINT
                  AND is_visible = FALSE
                """,
                int(workspace_id),
                int(user_id),
            )
        return frozenset(str(row["module_key"]) for row in rows)

    async def module_is_visible(
        self,
        *,
        workspace_id: int,
        user_id: int,
        module_key: str,
    ) -> bool:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT is_visible
                FROM workspace_user_module_preferences
                WHERE workspace_id = $1::BIGINT
                  AND user_id = $2::BIGINT
                  AND module_key = $3::VARCHAR
                """,
                int(workspace_id),
                int(user_id),
                module_key.strip(),
            )
        return True if value is None else bool(value)

    async def set_module_visible(
        self,
        *,
        workspace_id: int,
        user_id: int,
        module_key: str,
        is_visible: bool,
    ) -> bool:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                INSERT INTO workspace_user_module_preferences (
                    workspace_id, user_id, module_key, is_visible
                )
                VALUES ($1::BIGINT, $2::BIGINT, $3::VARCHAR, $4::BOOLEAN)
                ON CONFLICT (workspace_id, user_id, module_key) DO UPDATE
                SET is_visible = EXCLUDED.is_visible,
                    updated_at = NOW()
                RETURNING is_visible
                """,
                int(workspace_id),
                int(user_id),
                module_key.strip(),
                bool(is_visible),
            )
        return bool(value)

    async def provider_snapshot(
        self,
        provider: AufProvider,
    ) -> AufProviderSnapshot:
        aliases = list(provider.model_aliases)
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = 'queued') AS queued,
                    COUNT(*) FILTER (WHERE status = 'running') AS running
                FROM ai_tasks
                WHERE task_type = 'media.generate.kie'
                  AND payload->'request'->>'model' = ANY($1::VARCHAR[])
                """,
                aliases,
            )
        return AufProviderSnapshot(
            provider=provider,
            queued=int(row["queued"] or 0) if row is not None else 0,
            running=int(row["running"] or 0) if row is not None else 0,
        )

    async def request_task_cancellation(
        self,
        *,
        task_id: UUID,
        requested_by_user_id: int,
        global_owner: bool,
    ) -> AufCancellationResult | None:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT id, status, payload, created_by
                    FROM ai_tasks
                    WHERE id = $1::UUID
                      AND task_type = 'media.generate.kie'
                    FOR UPDATE
                    """,
                    task_id,
                )
                if row is None:
                    return None
                payload = _mapping(row["payload"])
                owner_id = _optional_int(payload.get("user_id")) or _optional_int(
                    row["created_by"]
                )
                if not global_owner and owner_id != int(requested_by_user_id):
                    raise PermissionError("Можно отменять только свои задачи Ауф.")
                status = str(row["status"])
                campaign = _mapping(payload.get("kie_campaign"))
                provider_started = bool(campaign.get("active_provider_task_id"))
                if status == AITaskStatus.QUEUED.value:
                    await connection.execute(
                        """
                        UPDATE ai_tasks
                        SET status = 'cancelled',
                            last_error_type = 'CancelledByUser',
                            last_error = 'Cancelled before provider submission.',
                            completed_at = NOW(),
                            updated_at = NOW()
                        WHERE id = $1::UUID
                          AND status = 'queued'
                        """,
                        task_id,
                    )
                    return AufCancellationResult(
                        task_id=task_id,
                        status=AITaskStatus.CANCELLED.value,
                        cancel_requested=True,
                        provider_task_started=False,
                    )
                if status == AITaskStatus.RUNNING.value:
                    payload["cancel_requested"] = True
                    payload["cancel_requested_by"] = int(requested_by_user_id)
                    payload["cancel_requested_at"] = datetime.now(
                        timezone.utc
                    ).isoformat()
                    await connection.execute(
                        """
                        UPDATE ai_tasks
                        SET payload = $2::JSONB,
                            updated_at = NOW()
                        WHERE id = $1::UUID
                          AND status = 'running'
                        """,
                        task_id,
                        json.dumps(payload, ensure_ascii=False, default=str),
                    )
                    return AufCancellationResult(
                        task_id=task_id,
                        status=AITaskStatus.RUNNING.value,
                        cancel_requested=True,
                        provider_task_started=provider_started,
                    )
                return AufCancellationResult(
                    task_id=task_id,
                    status=status,
                    cancel_requested=bool(payload.get("cancel_requested")),
                    provider_task_started=provider_started,
                )

    async def cancellation_requested(self, task_id: UUID) -> bool:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT COALESCE((payload->>'cancel_requested')::BOOLEAN, FALSE)
                FROM ai_tasks
                WHERE id = $1::UUID
                """,
                task_id,
            )
        return bool(value)


def _runtime_from_row(row: Mapping[str, Any]) -> AufRuntimeSettings:
    return AufRuntimeSettings(
        kie_concurrency_limit=int(row["kie_concurrency_limit"]),
        grs_concurrency_limit=int(row["grs_concurrency_limit"]),
        workspace_default_limit=int(row["workspace_default_limit"]),
        workspace_max_limit=int(row["workspace_max_limit"]),
        configured=bool(row["configured"]),
        setup_notice_sent_at=row["setup_notice_sent_at"],
        updated_by_user_id=_optional_int(row["updated_by_user_id"]),
        updated_at=row["updated_at"],
    )


def _workspace_from_row(row: Mapping[str, Any]) -> WorkspaceAufSettings:
    return WorkspaceAufSettings(
        workspace_id=int(row["workspace_id"]),
        concurrency_limit=int(row["concurrency_limit"]),
        updated_by_user_id=_optional_int(row["updated_by_user_id"]),
        updated_at=row["updated_at"],
    )


def _mapping(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(decoded, Mapping):
            return dict(decoded)
    return {}


def _optional_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


__all__ = ("AufRuntimeRepository",)

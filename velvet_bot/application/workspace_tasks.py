from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from velvet_bot.database import Database
from velvet_bot.domains.media_generation import KIE_GENERATION_TASK_TYPE


async def list_owned_workspace_tasks(
    database: Database,
    *,
    workspace_id: int,
    actor_user_id: int,
    offset: int,
    page_size: int,
):
    """List one owned workspace task page plus a look-ahead row."""

    if page_size < 1:
        raise ValueError("page_size must be positive")
    async with database.acquire() as connection:
        return await connection.fetch(
            """
            SELECT
                task.id,
                task.status,
                task.payload,
                task.result,
                task.attempt_count,
                task.created_at,
                task.completed_at,
                charge.quoted_units,
                charge.captured_units,
                charge.status AS charge_status
            FROM ai_tasks AS task
            LEFT JOIN auf_task_charges AS charge ON charge.task_id = task.id
            WHERE task.task_type = $1::VARCHAR
              AND task.created_by = $2::BIGINT
              AND task.payload ->> 'workspace_id' = $3::TEXT
            ORDER BY task.created_at DESC, task.id DESC
            LIMIT $4::INTEGER OFFSET $5::INTEGER
            """,
            KIE_GENERATION_TASK_TYPE,
            int(actor_user_id),
            str(int(workspace_id)),
            int(page_size) + 1,
            max(0, int(offset)),
        )


async def get_owned_success_task(
    database: Database,
    *,
    task_id: UUID,
    workspace_id: int,
    actor_user_id: int,
):
    """Load a successful task only when it belongs to the actor and workspace."""

    async with database.acquire() as connection:
        return await connection.fetchrow(
            """
            SELECT
                task.id,
                task.status,
                task.payload,
                task.result,
                task.attempt_count,
                task.created_at,
                task.completed_at,
                charge.quoted_units,
                charge.captured_units,
                charge.status AS charge_status
            FROM ai_tasks AS task
            LEFT JOIN auf_task_charges AS charge ON charge.task_id = task.id
            WHERE task.id = $1::UUID
              AND task.task_type = $2::VARCHAR
              AND task.status = 'success'
              AND task.created_by = $3::BIGINT
              AND task.payload ->> 'workspace_id' = $4::TEXT
            """,
            task_id,
            KIE_GENERATION_TASK_TYPE,
            int(actor_user_id),
            str(int(workspace_id)),
        )


async def load_task_results(
    database: Database,
    task_ids: Sequence[UUID],
) -> dict[UUID, object]:
    """Load persisted result payloads for an already-authorized task page."""

    if not task_ids:
        return {}
    async with database.acquire() as connection:
        rows = await connection.fetch(
            "SELECT id, result FROM ai_tasks WHERE id = ANY($1::UUID[])",
            list(task_ids),
        )
    return {row["id"]: row["result"] for row in rows}


__all__ = (
    "get_owned_success_task",
    "list_owned_workspace_tasks",
    "load_task_results",
)

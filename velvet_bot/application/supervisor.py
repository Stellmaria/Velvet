from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from velvet_bot.supervisor_client import SupervisorClient, SupervisorClientError


@dataclass(frozen=True, slots=True)
class SupervisorTaskList:
    tasks: tuple[dict[str, Any], ...]
    enabled: bool


async def load_supervisor_status(client: SupervisorClient) -> dict[str, Any]:
    return await client.status()


async def load_supervisor_tasks(
    client: SupervisorClient,
    *,
    limit: int = 20,
) -> SupervisorTaskList:
    payload = await client.codex_tasks(limit=limit)
    raw_tasks = payload.get("tasks", [])
    tasks = tuple(item for item in raw_tasks if isinstance(item, dict)) if isinstance(raw_tasks, list) else ()
    try:
        status_payload = await client.status()
        enabled = bool(
            status_payload.get("status", {}).get("codex", {}).get("enabled")
        )
    except SupervisorClientError:
        # The task endpoint already answered successfully.  Do not hide that
        # useful result merely because the optional status request failed.
        enabled = True
    return SupervisorTaskList(tasks=tasks, enabled=enabled)


async def load_supervisor_task(
    client: SupervisorClient,
    task_id: str,
) -> dict[str, Any]:
    cleaned = task_id.strip()
    if not cleaned:
        raise ValueError("ID задачи не указан.")
    payload = await client.codex_task(cleaned)
    task = payload.get("task", {})
    if not isinstance(task, dict):
        raise SupervisorClientError("Supervisor вернул некорректную задачу Codex.")
    return task


async def create_supervisor_task(
    client: SupervisorClient,
    *,
    prompt: str,
    requested_by: str,
) -> dict[str, Any]:
    cleaned = prompt.strip()
    if not cleaned:
        raise ValueError("Описание задачи не может быть пустым.")
    payload = await client.create_codex_task(
        prompt=cleaned,
        requested_by=requested_by,
    )
    task = payload.get("task", {})
    if not isinstance(task, dict):
        raise SupervisorClientError("Supervisor вернул некорректную задачу Codex.")
    return task


__all__ = (
    "SupervisorTaskList",
    "create_supervisor_task",
    "load_supervisor_status",
    "load_supervisor_task",
    "load_supervisor_tasks",
)

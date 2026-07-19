from __future__ import annotations

from typing import Any

from aiogram import Router

from velvet_bot.application.supervisor import (
    load_supervisor_status,
    load_supervisor_tasks,
)
from velvet_bot.presentation.telegram.routers.supervisor.codex import (
    router as codex_router,
)
from velvet_bot.presentation.telegram.routers.supervisor.console import (
    router as console_router,
)
from velvet_bot.presentation.telegram.routers.supervisor.git import router as git_router
from velvet_bot.presentation.telegram.routers.supervisor.logs import router as logs_router
from velvet_bot.presentation.telegram.routers.supervisor.process import (
    router as process_router,
)
from velvet_bot.presentation.telegram.routers.supervisor.self_control import (
    router as self_router,
)
from velvet_bot.presentation.telegram.routers.supervisor.status import (
    router as status_router,
    show_supervisor_menu,
)
from velvet_bot.presentation.telegram.supervisor.contract import (
    SupervisorCallback,
    SupervisorReplyMarkerFilter,
    supervisor_callback,
)
from velvet_bot.presentation.telegram.supervisor.views import (
    _accepted_keyboard,
    _answer_error,
    _bot_keyboard,
    _bot_text,
    _codex_keyboard,
    _confirm_keyboard,
    _git_keyboard,
    _git_text,
    _logs_keyboard,
    _logs_text,
    _main_keyboard,
    _operation_accepted,
    _safe_edit,
    _status_text,
    _task_keyboard,
    _task_status_label,
    _task_text,
    _tasks_text,
    _unavailable_text,
)
from velvet_bot.supervisor_client import SupervisorClient

router = Router(name=__name__)
router.include_router(status_router)
router.include_router(process_router)
router.include_router(git_router)
router.include_router(logs_router)
# Console must be registered before the historical broad reply-marker handler in
# codex so SUPERVISOR_INPUT:console is consumed by its focused route.
router.include_router(console_router)
router.include_router(self_router)
router.include_router(codex_router)

# Compatibility aliases for tests and older imports. Operational routes live in
# the focused controllers above; this module is only the composition boundary.
_cb = supervisor_callback


async def _load_status(client: SupervisorClient) -> dict[str, Any]:
    return await load_supervisor_status(client)


async def _load_tasks(client: SupervisorClient) -> tuple[list[dict[str, Any]], bool]:
    result = await load_supervisor_tasks(client)
    return list(result.tasks), result.enabled


__all__ = (
    "SupervisorCallback",
    "SupervisorReplyMarkerFilter",
    "router",
    "show_supervisor_menu",
)

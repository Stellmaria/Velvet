from __future__ import annotations

import contextvars
import importlib
from typing import Any

from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from velvet_bot.domains.ai_usage import AITaskQueueService
from velvet_bot.domains.media_generation.friendly_worker import FriendlyKieGenerationWorker
from velvet_bot.domains.media_generation.models import KIE_GENERATION_TASK_TYPE
from velvet_bot.presentation.telegram.routers.workspace_meow_runtime import (
    build_task_cancel_keyboard,
)

_INSTALLED = False
_LATEST_TASK: contextvars.ContextVar[tuple[str, int] | None] = contextvars.ContextVar(
    "latest_auf_task",
    default=None,
)


def _with_cancel_row(
    reply_markup: InlineKeyboardMarkup | None,
    *,
    task_id: str,
    workspace_id: int,
) -> InlineKeyboardMarkup:
    cancel = build_task_cancel_keyboard(
        workspace_id=workspace_id,
        task_id=task_id,
    ).inline_keyboard
    rows = list(cancel)
    if reply_markup is not None:
        rows.extend(reply_markup.inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def install_auf_cancel_ui() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_enqueue = AITaskQueueService.enqueue

    async def enqueue_with_task_context(self, request):
        result = await original_enqueue(self, request)
        if request.task_type == KIE_GENERATION_TASK_TYPE:
            workspace_id = int(request.payload.get("workspace_id") or 0)
            _LATEST_TASK.set((str(result.task.id), workspace_id))
        return result

    AITaskQueueService.enqueue = enqueue_with_task_context

    # These module paths remain stable until the generation routers themselves are
    # moved behind canonical Auf wrappers.
    photo = importlib.import_module(
        "velvet_bot.presentation.telegram.routers.workspace_meow"
    )
    video = importlib.import_module(
        "velvet_bot.presentation.telegram.routers.workspace_meow_video"
    )

    def patch_edit(module: Any) -> None:
        original_edit = module._edit_or_answer

        async def edit_with_cancel(callback, *, text: str, reply_markup):
            latest = _LATEST_TASK.get()
            if latest is not None and "Задача" in text and (
                "поставлена в очередь" in text or "запущена" in text
            ):
                task_id, workspace_id = latest
                reply_markup = _with_cancel_row(
                    reply_markup,
                    task_id=task_id,
                    workspace_id=workspace_id,
                )
                _LATEST_TASK.set(None)
            await original_edit(
                callback,
                text=text,
                reply_markup=reply_markup,
            )

        module._edit_or_answer = edit_with_cancel

    patch_edit(photo)
    patch_edit(video)

    original_start = FriendlyKieGenerationWorker._start_progress
    original_publish = FriendlyKieGenerationWorker._publish_progress

    async def start_progress_with_cancel(self, *, task, request):
        progress = await original_start(self, task=task, request=request)
        if progress is None or progress.message_id is None:
            return progress
        workspace_id = int(task.payload.get("workspace_id") or 0)
        try:
            await self._bot.edit_message_reply_markup(
                chat_id=progress.chat_id,
                message_id=progress.message_id,
                reply_markup=build_task_cancel_keyboard(
                    workspace_id=workspace_id,
                    task_id=task.id,
                ),
            )
        except TelegramAPIError:
            pass
        return progress

    async def publish_progress_with_cancel(
        self,
        progress,
        *,
        task,
        request,
        percent: int,
        stage: str,
        force: bool = False,
    ) -> None:
        await original_publish(
            self,
            progress,
            task=task,
            request=request,
            percent=percent,
            stage=stage,
            force=force,
        )
        if progress is None or progress.message_id is None:
            return
        workspace_id = int(task.payload.get("workspace_id") or 0)
        markup = (
            None
            if int(percent) >= 100
            else build_task_cancel_keyboard(
                workspace_id=workspace_id,
                task_id=task.id,
            )
        )
        try:
            await self._bot.edit_message_reply_markup(
                chat_id=progress.chat_id,
                message_id=progress.message_id,
                reply_markup=markup,
            )
        except TelegramAPIError:
            pass

    FriendlyKieGenerationWorker._start_progress = start_progress_with_cancel
    FriendlyKieGenerationWorker._publish_progress = publish_progress_with_cancel
    _INSTALLED = True


__all__ = ("install_auf_cancel_ui",)

from __future__ import annotations

import os
from typing import Any

from velvet_bot.domains.codex_image import CodexImageClient, CodexImageWorker
from velvet_bot.workers import PeriodicWorkerSpec

_INSTALLED = False


def _enabled() -> bool:
    return os.getenv("CODEX_IMAGE_ENABLED", "false").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
        "да",
    }


def install_gpt_image_2_bootstrap() -> None:
    """Attach the one-shot GPT Image 2 worker without duplicating app bootstrap."""
    global _INSTALLED
    if _INSTALLED:
        return
    from velvet_bot.app import bootstrap

    original = bootstrap.build_worker_manager

    def build_worker_manager_with_gpt_image_2(*args: Any, **kwargs: Any):
        manager = original(*args, **kwargs)
        if not _enabled():
            return manager
        queue = kwargs.get("ai_task_queue_service")
        bot = kwargs.get("bot")
        if queue is None or bot is None:
            raise RuntimeError("GPT Image 2 worker требует bot и ai_task_queue_service.")
        worker = CodexImageWorker(
            bot=bot,
            queue=queue,
            client=CodexImageClient(),
        )
        manager.register(
            PeriodicWorkerSpec(
                name="codex-image-generation",
                description="GPT Image 2 через Codex Plus · одна генерация",
                interval_seconds=2,
                runner=worker.process_once,
            )
        )
        return manager

    bootstrap.build_worker_manager = build_worker_manager_with_gpt_image_2
    _INSTALLED = True


__all__ = ("install_gpt_image_2_bootstrap",)

from __future__ import annotations

import logging
import os
from typing import Any

from velvet_bot.domains.codex_image import CodexImageClient, CodexImageWorker
from velvet_bot.workers import PeriodicWorkerSpec

_INSTALLED = False
_FINALIZED = False
_WORKER_NAME = "codex-image-generation"
logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return os.getenv("CODEX_IMAGE_ENABLED", "false").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
        "да",
    }


def _finalize_worker_builder() -> None:
    """Wrap the fully composed worker builder immediately before app startup."""
    global _FINALIZED
    if _FINALIZED:
        return

    from velvet_bot.app import bootstrap
    from velvet_bot.app import workers as workers_module

    original = workers_module.build_worker_manager

    def build_worker_manager_with_gpt_image_2(*args: Any, **kwargs: Any):
        manager = original(*args, **kwargs)
        if not _enabled() or _WORKER_NAME in manager.registered_names():
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
                name=_WORKER_NAME,
                description="GPT Image 2 через Codex Plus · одна генерация",
                interval_seconds=2,
                runner=worker.process_once,
            )
        )
        logger.info("Installed GPT Image 2 worker runtime name=%s", _WORKER_NAME)
        return manager

    workers_module.build_worker_manager = build_worker_manager_with_gpt_image_2
    bootstrap.build_worker_manager = build_worker_manager_with_gpt_image_2
    _FINALIZED = True


def install_gpt_image_2_bootstrap() -> None:
    """Finalize the GPT Image 2 worker after all feature wrappers are installed."""
    global _INSTALLED
    if _INSTALLED:
        return

    from velvet_bot.app import bootstrap

    original_run_application = bootstrap.run_application

    async def run_application_with_gpt_image_2() -> None:
        _finalize_worker_builder()
        await original_run_application()

    bootstrap.run_application = run_application_with_gpt_image_2
    _INSTALLED = True


__all__ = ("install_gpt_image_2_bootstrap",)

from __future__ import annotations

import importlib
import logging

from velvet_bot.domains.auf_wallet import build_auf_charged_task_queue_service

logger = logging.getLogger(__name__)
_INSTALLED = False


def install_auf_charged_queue() -> None:
    """Make the production bootstrap use the atomic Auf wallet queue."""

    global _INSTALLED
    if _INSTALLED:
        return
    bootstrap = importlib.import_module("velvet_bot.app.bootstrap")
    bootstrap.build_ai_task_queue_service = build_auf_charged_task_queue_service
    logger.info("Installed charged Auf task queue in production bootstrap")
    _INSTALLED = True


__all__ = ("install_auf_charged_queue",)

"""Compatibility aliases for the retired Meow charged queue names."""

from velvet_bot.domains.auf_wallet.charged_queue import (
    AufChargedTaskQueueService,
    build_auf_charged_task_queue_service,
)

AufChargedTaskQueueService = AufChargedTaskQueueService
build_auf_charged_task_queue_service = build_auf_charged_task_queue_service

__all__ = (
    "AufChargedTaskQueueService",
    "build_auf_charged_task_queue_service",
)

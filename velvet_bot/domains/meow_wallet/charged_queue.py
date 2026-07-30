"""Compatibility aliases for the retired Meow charged queue names."""
from velvet_bot.domains.auf_wallet.charged_queue import (
    AufChargedTaskQueueService, build_auf_charged_task_queue_service,
)
MeowChargedTaskQueueService = AufChargedTaskQueueService
build_auf_charged_task_queue_service = build_auf_charged_task_queue_service
__all__ = (
    "MeowChargedTaskQueueService",
    "build_auf_charged_task_queue_service",
)

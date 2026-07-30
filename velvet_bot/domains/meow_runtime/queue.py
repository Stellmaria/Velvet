"""Compatibility alias for the retired Meow provider queue name."""

from velvet_bot.domains.auf_runtime.queue import ProviderAufTaskQueueService

ProviderMeowTaskQueueService = ProviderAufTaskQueueService

__all__ = ("ProviderMeowTaskQueueService",)

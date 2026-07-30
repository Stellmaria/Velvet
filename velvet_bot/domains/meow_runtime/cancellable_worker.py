"""Compatibility aliases for the retired Meow cancellable worker names."""

from velvet_bot.domains.auf_runtime.cancellable_worker import (
    AufCancellationRequested,
    build_cancellable_worker_class,
)

MeowCancellationRequested = AufCancellationRequested

__all__ = (
    "MeowCancellationRequested",
    "build_cancellable_worker_class",
)

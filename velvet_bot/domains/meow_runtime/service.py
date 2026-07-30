"""Compatibility aliases for the retired Meow runtime service names."""

from velvet_bot.domains.auf_runtime.service import (
    AufRuntimeAccessError,
    AufRuntimeService,
)

MeowRuntimeAccessError = AufRuntimeAccessError
MeowRuntimeService = AufRuntimeService

__all__ = (
    "MeowRuntimeAccessError",
    "MeowRuntimeService",
)

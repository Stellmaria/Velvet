"""Compatibility aliases for the retired Meow dispatcher names."""

from velvet_bot.domains.auf_runtime.dispatcher import (
    AufGenerationDispatcher,
    ProviderAwareKieClient,
)

MeowGenerationDispatcher = AufGenerationDispatcher

__all__ = (
    "MeowGenerationDispatcher",
    "ProviderAwareKieClient",
)

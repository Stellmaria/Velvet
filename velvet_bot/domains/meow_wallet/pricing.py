"""Compatibility aliases for retired Meow pricing names."""
from velvet_bot.domains.auf_wallet.pricing import (
    AufPriceNotConfigured, AufPriceQuote, AufPricingRepository,
    quote_auf_payload,
)
MeowPriceNotConfigured = AufPriceNotConfigured
MeowPriceQuote = AufPriceQuote
MeowPricingRepository = AufPricingRepository
quote_meow_payload = quote_auf_payload
__all__ = (
    "MeowPriceNotConfigured", "MeowPriceQuote",
    "MeowPricingRepository", "quote_meow_payload",
)

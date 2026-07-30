"""Compatibility aliases for retired Meow pricing names."""

from velvet_bot.domains.auf_wallet.pricing import (
    AufPriceNotConfigured,
    AufPriceQuote,
    AufPricingRepository,
    quote_auf_payload,
)

AufPriceNotConfigured = AufPriceNotConfigured
AufPriceQuote = AufPriceQuote
AufPricingRepository = AufPricingRepository
quote_auf_payload = quote_auf_payload

__all__ = (
    "AufPriceNotConfigured", "AufPriceQuote",
    "AufPricingRepository", "quote_auf_payload",
)

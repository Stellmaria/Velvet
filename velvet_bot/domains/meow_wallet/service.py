"""Compatibility aliases for retired Meow wallet service names."""

from velvet_bot.domains.auf_wallet.service import (
    AUF_PACKAGES,
    AufPackageQuote,
    AufWalletAccessError,
    AufWalletService,
)

MeowAufPackageQuote = AufPackageQuote
MeowWalletAccessError = AufWalletAccessError
MeowWalletService = AufWalletService

__all__ = (
    "AUF_PACKAGES",
    "MeowAufPackageQuote",
    "MeowWalletAccessError",
    "MeowWalletService",
)

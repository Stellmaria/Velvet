"""Compatibility aliases for retired Meow wallet service names."""

from velvet_bot.domains.auf_wallet.service import (
    AUF_PACKAGES,
    AufPackageQuote,
    AufWalletAccessError,
    AufWalletService,
)

AufPackageQuote = AufPackageQuote
AufWalletAccessError = AufWalletAccessError
AufWalletService = AufWalletService

__all__ = (
    "AUF_PACKAGES", "AufPackageQuote",
    "AufWalletAccessError", "AufWalletService",
)

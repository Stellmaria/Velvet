"""Compatibility package for retired Meow wallet imports.

All implementations live in :mod:`velvet_bot.domains.auf_wallet`.
"""

from velvet_bot.domains.auf_wallet import (
    AUF_PACKAGES,
    AUF_SCALE,
    AufEconomySettings,
    AufInsufficientBalance,
    AufPackageQuote,
    AufWallet,
    AufWalletAccessError,
    AufWalletEntry,
    AufWalletError,
    AufWalletFrozen,
    AufWalletOperation,
    AufWalletOverview,
    AufWalletRepository,
    AufWalletService,
    AufWalletStatus,
    auf_to_units,
    format_auf_units,
    units_to_auf,
)

MeowAufPackageQuote = AufPackageQuote
MeowEconomySettings = AufEconomySettings
MeowInsufficientBalance = AufInsufficientBalance
MeowWallet = AufWallet
MeowWalletAccessError = AufWalletAccessError
MeowWalletEntry = AufWalletEntry
MeowWalletError = AufWalletError
MeowWalletFrozen = AufWalletFrozen
MeowWalletOperation = AufWalletOperation
MeowWalletOverview = AufWalletOverview
MeowWalletRepository = AufWalletRepository
MeowWalletService = AufWalletService
MeowWalletStatus = AufWalletStatus

__all__ = (
    "AUF_PACKAGES",
    "AUF_SCALE",
    "MeowAufPackageQuote",
    "MeowEconomySettings",
    "MeowInsufficientBalance",
    "MeowWallet",
    "MeowWalletAccessError",
    "MeowWalletEntry",
    "MeowWalletError",
    "MeowWalletFrozen",
    "MeowWalletOperation",
    "MeowWalletOverview",
    "MeowWalletRepository",
    "MeowWalletService",
    "MeowWalletStatus",
    "auf_to_units",
    "format_auf_units",
    "units_to_auf",
)

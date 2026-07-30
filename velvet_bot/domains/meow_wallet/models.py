"""Compatibility aliases for retired Meow wallet model names."""

from velvet_bot.domains.auf_wallet.models import (
    AUF_SCALE,
    AufEconomySettings,
    AufInsufficientBalance,
    AufWallet,
    AufWalletEntry,
    AufWalletError,
    AufWalletFrozen,
    AufWalletOperation,
    AufWalletOverview,
    AufWalletStatus,
    auf_to_units,
    format_auf_units,
    units_to_auf,
)

MeowEconomySettings = AufEconomySettings
MeowInsufficientBalance = AufInsufficientBalance
MeowWallet = AufWallet
MeowWalletEntry = AufWalletEntry
MeowWalletError = AufWalletError
MeowWalletFrozen = AufWalletFrozen
MeowWalletOperation = AufWalletOperation
MeowWalletOverview = AufWalletOverview
MeowWalletStatus = AufWalletStatus

__all__ = (
    "AUF_SCALE", "MeowEconomySettings", "MeowInsufficientBalance",
    "MeowWallet", "MeowWalletEntry", "MeowWalletError",
    "MeowWalletFrozen", "MeowWalletOperation", "MeowWalletOverview",
    "MeowWalletStatus", "auf_to_units", "format_auf_units", "units_to_auf",
)

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

AufEconomySettings = AufEconomySettings
AufInsufficientBalance = AufInsufficientBalance
AufWallet = AufWallet
AufWalletEntry = AufWalletEntry
AufWalletError = AufWalletError
AufWalletFrozen = AufWalletFrozen
AufWalletOperation = AufWalletOperation
AufWalletOverview = AufWalletOverview
AufWalletStatus = AufWalletStatus

__all__ = (
    "AUF_SCALE", "AufEconomySettings", "AufInsufficientBalance",
    "AufWallet", "AufWalletEntry", "AufWalletError",
    "AufWalletFrozen", "AufWalletOperation", "AufWalletOverview",
    "AufWalletStatus", "auf_to_units", "format_auf_units", "units_to_auf",
)

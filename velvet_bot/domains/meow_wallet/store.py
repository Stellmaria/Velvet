"""Compatibility alias for the retired Meow wallet repository name."""

from velvet_bot.domains.auf_wallet.store import (
    AufWalletRepository,
    _ensure_wallet,
    _wallet_from_row,
)

MeowWalletRepository = AufWalletRepository

__all__ = ("MeowWalletRepository",)

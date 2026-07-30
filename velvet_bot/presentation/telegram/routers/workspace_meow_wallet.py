"""Compatibility alias for the retired Meow wallet router path."""

from velvet_bot.presentation.telegram.routers.workspace_auf_wallet import (
    handle_auf_wallet_action,
)

handle_meow_wallet_action = handle_auf_wallet_action

__all__ = ("handle_auf_wallet_action", "handle_meow_wallet_action")

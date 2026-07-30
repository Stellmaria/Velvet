"""Compatibility shim for the retired Meow wallet UI installer name."""
from velvet_bot.app.auf_wallet_ui_install import install_auf_wallet_ui
install_meow_wallet_ui = install_auf_wallet_ui
__all__ = ("install_auf_wallet_ui", "install_meow_wallet_ui")

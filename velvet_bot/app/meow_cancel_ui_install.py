"""Compatibility shim for the pre-Auf task cancellation installer name."""

from velvet_bot.app.auf_cancel_ui_install import install_auf_cancel_ui

install_meow_cancel_ui = install_auf_cancel_ui

__all__ = (
    "install_auf_cancel_ui",
    "install_meow_cancel_ui",
)

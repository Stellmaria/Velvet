"""Compatibility shim for the pre-Auf workspace UI installer name."""

from velvet_bot.app.auf_workspace_ui_install import install_auf_workspace_ui

install_meow_workspace_ui = install_auf_workspace_ui

__all__ = (
    "install_auf_workspace_ui",
    "install_meow_workspace_ui",
)

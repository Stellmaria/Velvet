"""Compatibility shim for the pre-Auf runtime installer name."""

from velvet_bot.app.auf_runtime_install import install_auf_runtime_dispatcher

install_meow_runtime_dispatcher = install_auf_runtime_dispatcher

__all__ = (
    "install_auf_runtime_dispatcher",
    "install_meow_runtime_dispatcher",
)

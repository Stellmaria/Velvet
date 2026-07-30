"""Compatibility shim for the pre-Auf reconciliation installer name."""

from velvet_bot.app.auf_reconciliation_install import install_auf_reconciliation

install_meow_reconciliation = install_auf_reconciliation

__all__ = (
    "install_auf_reconciliation",
    "install_meow_reconciliation",
)

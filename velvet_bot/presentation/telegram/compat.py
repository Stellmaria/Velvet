from __future__ import annotations

from velvet_bot.runtime_log_hotfixes import install_runtime_log_hotfixes
from velvet_bot.safe_analytics_edit import install_safe_analytics_edit

_INSTALLED = False


def install_legacy_compatibility() -> None:
    """Install temporary bridges kept until their domains are fully migrated."""
    global _INSTALLED
    if _INSTALLED:
        return

    install_runtime_log_hotfixes()
    install_safe_analytics_edit()
    _INSTALLED = True


__all__ = ("install_legacy_compatibility",)

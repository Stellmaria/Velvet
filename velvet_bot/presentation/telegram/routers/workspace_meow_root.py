"""Compatibility module for the retired workspace_meow_root path."""

from velvet_bot.presentation.telegram.routers import workspace_auf_root as _canonical
from velvet_bot.presentation.telegram.routers.workspace_auf_root import *  # noqa: F403

def __getattr__(name: str):
    direct = getattr(_canonical, name, None)
    if direct is not None:
        return direct
    mapped = name.replace("Meow", "Auf").replace("meow", "auf")
    return getattr(_canonical, mapped)

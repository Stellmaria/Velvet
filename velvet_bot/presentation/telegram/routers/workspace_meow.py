"""Compatibility module for the retired workspace_meow path."""

from velvet_bot.presentation.telegram.routers import workspace_auf as _canonical
from velvet_bot.presentation.telegram.routers.workspace_auf import *  # noqa: F403
from velvet_bot.presentation.telegram.routers.workspace_auf_legacy import (
    LegacyMeowCallback as MeowCallback,
    MeowForm,
)


def __getattr__(name: str):
    direct = getattr(_canonical, name, None)
    if direct is not None:
        return direct
    mapped = name.replace("Meow", "Auf").replace("meow", "auf")
    return getattr(_canonical, mapped)

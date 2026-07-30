"""Compatibility module for the retired workspace_meow_video path."""

from velvet_bot.presentation.telegram.routers import workspace_auf_video as _canonical
from velvet_bot.presentation.telegram.routers.workspace_auf_video import *  # noqa: F403
from velvet_bot.presentation.telegram.routers.workspace_auf_legacy import (
    LegacyMeowVideoCallback as MeowVideoCallback,
    MeowVideoForm,
)


def __getattr__(name: str):
    direct = getattr(_canonical, name, None)
    if direct is not None:
        return direct
    mapped = name.replace("Meow", "Auf").replace("meow", "auf")
    return getattr(_canonical, mapped)

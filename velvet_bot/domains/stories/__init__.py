from __future__ import annotations

from importlib import import_module
from typing import Final, cast

from velvet_bot.domains.stories.catalog import (
    clean_story_short_label,
    clean_story_title,
    format_story_release,
    make_story_key,
    universe_requires_story,
)
from velvet_bot.domains.stories.constants import (
    KNOWN_UNIVERSES,
    RELEASE_PRECISIONS,
    STORY_REQUIRED_UNIVERSES,
)
from velvet_bot.domains.stories.models import (
    AssignedCharacterStory,
    CharacterStory,
    StoryPage,
    StorySummary,
)

_RUNTIME_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "StoryRepository": (
        "velvet_bot.domains.stories.repository",
        "StoryRepository",
    ),
    "StoryService": (
        "velvet_bot.domains.stories.service",
        "StoryService",
    ),
}

__all__ = (
    "KNOWN_UNIVERSES",
    "RELEASE_PRECISIONS",
    "STORY_REQUIRED_UNIVERSES",
    "AssignedCharacterStory",
    "CharacterStory",
    "StoryPage",
    "StoryRepository",
    "StoryService",
    "StorySummary",
    "clean_story_short_label",
    "clean_story_title",
    "format_story_release",
    "make_story_key",
    "universe_requires_story",
)


def __getattr__(name: str) -> object:
    target = _RUNTIME_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute_name = target
    value = cast(object, getattr(import_module(module_name), attribute_name))
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))

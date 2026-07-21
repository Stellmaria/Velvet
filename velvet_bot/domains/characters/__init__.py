from __future__ import annotations

from importlib import import_module
from typing import Final, cast

from velvet_bot.domains.characters.catalog import (
    category_label,
    normalize_category,
    normalize_universe,
    story_label,
    universe_label,
    validate_prompt_post_url,
)
from velvet_bot.domains.characters.constants import (
    CATEGORY_EMOJI,
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    GAME_UNIVERSE_ORDER,
    UNIVERSE_EMOJI,
    UNIVERSE_LABELS,
    UNIVERSE_ORDER,
    UNIVERSE_VALUE_ORDER,
)
from velvet_bot.domains.characters.models import (
    CategorySummary,
    CharacterDirectoryItem,
    CharacterDirectoryPage,
    CharacterRecord,
    UniverseSummary,
)

_RUNTIME_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "CharacterDirectoryRepository": (
        "velvet_bot.domains.characters.repository",
        "CharacterDirectoryRepository",
    ),
    "CharacterDirectoryService": (
        "velvet_bot.domains.characters.service",
        "CharacterDirectoryService",
    ),
}

__all__ = (
    "CATEGORY_EMOJI",
    "CATEGORY_LABELS",
    "CATEGORY_ORDER",
    "GAME_UNIVERSE_ORDER",
    "UNIVERSE_EMOJI",
    "UNIVERSE_LABELS",
    "UNIVERSE_ORDER",
    "UNIVERSE_VALUE_ORDER",
    "CategorySummary",
    "CharacterDirectoryItem",
    "CharacterDirectoryPage",
    "CharacterDirectoryRepository",
    "CharacterDirectoryService",
    "CharacterRecord",
    "UniverseSummary",
    "category_label",
    "normalize_category",
    "normalize_universe",
    "story_label",
    "universe_label",
    "validate_prompt_post_url",
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

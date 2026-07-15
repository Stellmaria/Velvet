"""Velvet Telegram bot package."""

from __future__ import annotations


def _install_builtin_category_extensions() -> None:
    """Register composition categories shared by every archive interface."""
    from velvet_bot import character_directory

    if "mfm" in character_directory.CATEGORY_ORDER:
        return

    categories = list(character_directory.CATEGORY_ORDER)
    categories.insert(categories.index("mf") + 1, "mfm")
    character_directory.CATEGORY_ORDER = tuple(categories)
    character_directory.CATEGORY_LABELS["mfm"] = "МЖМ"
    character_directory.CATEGORY_EMOJI["mfm"] = "👨‍👩‍👨"
    character_directory._CATEGORY_ALIASES.update(
        {
            "мжм": "mfm",
            "mfm": "mfm",
        }
    )


_install_builtin_category_extensions()
del _install_builtin_category_extensions

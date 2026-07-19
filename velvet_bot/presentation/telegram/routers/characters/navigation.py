from __future__ import annotations

from velvet_bot.domains.characters.catalog import normalize_category


def resolve_directory_category(
    requested_category: str | None,
    item_category: str | None,
) -> str:
    """Return a canonical category for character-directory navigation.

    Callback payloads can outlive deployments and may contain an empty, localized,
    or otherwise stale category. Prefer the requested value when it is valid, then
    fall back to the character's current category, and finally to the explicit
    uncategorized section.
    """

    for candidate in (requested_category, item_category, "uncategorized"):
        if not candidate:
            continue
        try:
            return normalize_category(candidate, allow_uncategorized=True)
        except ValueError:
            continue
    return "uncategorized"


__all__ = ("resolve_directory_category",)

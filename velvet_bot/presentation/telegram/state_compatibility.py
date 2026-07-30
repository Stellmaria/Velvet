from __future__ import annotations

from collections.abc import Mapping


def state_value(
    data: Mapping[str, object],
    key: str,
    *,
    legacy_prefix: str = "meow_",
) -> object:
    """Read the current state key, then its documented legacy-prefix fallback."""

    if key in data:
        return data[key]
    if not key.startswith("auf_"):
        return None
    return data.get(key.replace("auf_", legacy_prefix, 1))


__all__ = ("state_value",)

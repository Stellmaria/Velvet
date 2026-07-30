from __future__ import annotations

import json
from collections.abc import Mapping


def task_payload_mapping(value: object) -> dict[str, object]:
    """Normalize persisted Mapping/JSON values without transport decisions."""

    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(decoded, Mapping):
            return dict(decoded)
    return {}


def task_result_urls(value: object) -> tuple[str, ...]:
    """Return normalized non-empty result URLs from a persisted task result."""

    result = task_payload_mapping(value)
    urls = result.get("result_urls")
    if not isinstance(urls, (list, tuple)):
        return ()
    return tuple(
        str(item).strip()
        for item in urls
        if item is not None and str(item).strip()
    )


__all__ = ("task_payload_mapping", "task_result_urls")

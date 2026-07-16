from __future__ import annotations

import re
import unicodedata
from datetime import date

from velvet_bot.domains.stories.constants import STORY_REQUIRED_UNIVERSES

_STORY_KEY_RE = re.compile(r"[^\w]+", re.UNICODE)


def universe_requires_story(universe: str | None) -> bool:
    return bool(universe and universe in STORY_REQUIRED_UNIVERSES)


def clean_story_short_label(value: str) -> str:
    cleaned = "".join(unicodedata.normalize("NFKC", value).upper().split())
    if not cleaned:
        raise ValueError("Сокращение истории не может быть пустым.")
    if len(cleaned) > 16:
        raise ValueError("Сокращение истории не должно быть длиннее 16 символов.")
    return cleaned


def clean_story_title(value: str) -> str:
    cleaned = " ".join(unicodedata.normalize("NFKC", value).split())
    if not cleaned:
        raise ValueError("Название истории не может быть пустым.")
    if len(cleaned) > 160:
        raise ValueError("Название истории не должно быть длиннее 160 символов.")
    return cleaned


def make_story_key(short_label: str) -> str:
    normalized = unicodedata.normalize("NFKC", short_label).casefold()
    key = _STORY_KEY_RE.sub("_", normalized).strip("_")
    if not key:
        raise ValueError("Не удалось сформировать ключ истории.")
    return key[:64]


def format_story_release(
    released_on: date | None,
    release_precision: str,
) -> str:
    if released_on is None or release_precision == "unknown":
        return "дата не указана"
    if release_precision == "year":
        return str(released_on.year)
    if release_precision == "month":
        return released_on.strftime("%m.%Y")
    return released_on.strftime("%d.%m.%Y")


__all__ = (
    "clean_story_short_label",
    "clean_story_title",
    "format_story_release",
    "make_story_key",
    "universe_requires_story",
)

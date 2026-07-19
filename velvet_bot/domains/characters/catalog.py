from __future__ import annotations

import re

from velvet_bot.domains.characters.constants import (
    CATEGORY_ALIASES,
    CATEGORY_LABELS,
    UNIVERSE_ALIASES,
    UNIVERSE_LABELS,
)

_PROMPT_URL_RE = re.compile(
    r"^https://t\.me/(?:c/\d+|[A-Za-z0-9_]+)/\d+(?:\?[^\s]+)?$",
    re.IGNORECASE,
)


def normalize_category(value: str, *, allow_uncategorized: bool = False) -> str:
    normalized = "".join(value.casefold().split())
    category = CATEGORY_ALIASES.get(normalized)
    if category is None or (category == "uncategorized" and not allow_uncategorized):
        allowed = "женский, мужской, мж, мжм, мм, жж"
        raise ValueError(f"Неизвестная категория. Доступны: {allowed}.")
    return category


def normalize_universe(value: str, *, allow_unassigned: bool = False) -> str:
    normalized = "".join(value.casefold().split())
    universe = UNIVERSE_ALIASES.get(normalized)
    if universe is None or (universe == "unassigned" and not allow_unassigned):
        allowed = "SHS, КР, ЛМ, ИДМ, BG3, RE, Лагерта, Original, Другое"
        raise ValueError(f"Неизвестная вселенная. Доступны: {allowed}.")
    return universe


def category_label(category: str | None) -> str:
    return CATEGORY_LABELS.get(
        category or "uncategorized",
        CATEGORY_LABELS["uncategorized"],
    )


def universe_label(universe: str | None) -> str:
    return UNIVERSE_LABELS.get(
        universe or "unassigned",
        UNIVERSE_LABELS["unassigned"],
    )


def story_label(
    story_short_label: str | None,
    story_title: str | None,
) -> str:
    if not story_title:
        return "Без истории"
    if story_short_label:
        return f"{story_short_label} · {story_title}"
    return story_title


def validate_prompt_post_url(value: str) -> str:
    cleaned = value.strip()
    if not _PROMPT_URL_RE.fullmatch(cleaned):
        raise ValueError(
            "Нужна ссылка на пост Telegram: https://t.me/channel/123 "
            "или https://t.me/c/1234567890/123."
        )
    return cleaned


__all__ = (
    "category_label",
    "normalize_category",
    "normalize_universe",
    "story_label",
    "universe_label",
    "validate_prompt_post_url",
)

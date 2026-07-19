from __future__ import annotations

import re

_REFERENCE_COMMAND_PATTERNS = (
    re.compile(
        r"^/refs?(?:@(?P<bot>[A-Za-z0-9_]+))?\s+(?P<name>.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^@(?P<bot>[A-Za-z0-9_]+)\s+/?refs?\s+(?P<name>.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^/?refs?\s+@(?P<bot>[A-Za-z0-9_]+)\s+(?P<name>.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^/?refs?\s+(?P<name>.+?)\s+@(?P<bot>[A-Za-z0-9_]+)$",
        re.IGNORECASE,
    ),
    re.compile(r"^/?refs?\s+(?P<name>.+)$", re.IGNORECASE),
)
_REFERENCE_ADD_COMMAND_PATTERNS = (
    re.compile(
        r"^/refadd(?:@(?P<bot>[A-Za-z0-9_]+))?\s+(?P<name>.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^@(?P<bot>[A-Za-z0-9_]+)\s+/?refadd\s+(?P<name>.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^/?refadd\s+@(?P<bot>[A-Za-z0-9_]+)\s+(?P<name>.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^/?refadd\s+(?P<name>.+?)\s+@(?P<bot>[A-Za-z0-9_]+)$",
        re.IGNORECASE,
    ),
    re.compile(r"^/?refadd\s+(?P<name>.+)$", re.IGNORECASE),
)


def _parse_addressed_character(
    text: str,
    bot_username: str,
    patterns: tuple[re.Pattern[str], ...],
) -> str | None:
    cleaned = " ".join(text.split())
    if not cleaned:
        return None
    expected_username = bot_username.lstrip("@").casefold()
    for pattern in patterns:
        match = pattern.fullmatch(cleaned)
        if match is None:
            continue
        addressed_bot = match.groupdict().get("bot")
        if (
            addressed_bot
            and expected_username
            and addressed_bot.casefold() != expected_username
        ):
            return None
        character_name = match.group("name").strip()
        return character_name or None
    return None


def parse_reference_character(text: str, bot_username: str) -> str | None:
    """Parse a reference-view command addressed to the current bot."""

    return _parse_addressed_character(text, bot_username, _REFERENCE_COMMAND_PATTERNS)


def parse_reference_add_character(text: str, bot_username: str) -> str | None:
    """Parse a reference-add command addressed to the current bot."""

    return _parse_addressed_character(
        text,
        bot_username,
        _REFERENCE_ADD_COMMAND_PATTERNS,
    )


def parse_reference_selector(value: str) -> tuple[str, int | None]:
    """Split ``character name [number]`` while preserving names with spaces."""

    cleaned = " ".join(value.split())
    if not cleaned:
        return "", None

    for pattern in (
        r"^(?P<name>.+?)\s+#(?P<index>\d+)$",
        r"^(?P<name>.+?)\s+(?P<index>\d+)$",
    ):
        match = re.fullmatch(pattern, cleaned)
        if match is not None:
            return match.group("name").strip(), int(match.group("index"))
    return cleaned, None


__all__ = (
    "parse_reference_add_character",
    "parse_reference_character",
    "parse_reference_selector",
)

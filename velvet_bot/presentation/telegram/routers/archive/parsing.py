from __future__ import annotations

import re

_GUEST_COMMAND_PATTERN = re.compile(
    r"^/save(?:@(?P<bot>[A-Za-z0-9_]+))?\s+(?P<name>.+)$",
    re.IGNORECASE,
)
_GUEST_MENTION_PREFIX_PATTERN = re.compile(
    r"^@(?P<bot>[A-Za-z0-9_]+)\s+/?save\s+(?P<name>.+)$",
    re.IGNORECASE,
)
_GUEST_MENTION_AFTER_SAVE_PATTERN = re.compile(
    r"^/?save\s+@(?P<bot>[A-Za-z0-9_]+)\s+(?P<name>.+)$",
    re.IGNORECASE,
)
_GUEST_MENTION_SUFFIX_PATTERN = re.compile(
    r"^/?save\s+(?P<name>.+?)\s+@(?P<bot>[A-Za-z0-9_]+)$",
    re.IGNORECASE,
)
_GUEST_PLAIN_PATTERN = re.compile(r"^/?save\s+(?P<name>.+)$", re.IGNORECASE)


def parse_guest_save_character(text: str, bot_username: str) -> str | None:
    """Return the character addressed by a guest-mode save command."""

    cleaned = " ".join(text.split())
    if not cleaned:
        return None
    expected_username = bot_username.lstrip("@").casefold()
    for pattern in (
        _GUEST_COMMAND_PATTERN,
        _GUEST_MENTION_PREFIX_PATTERN,
        _GUEST_MENTION_AFTER_SAVE_PATTERN,
        _GUEST_MENTION_SUFFIX_PATTERN,
        _GUEST_PLAIN_PATTERN,
    ):
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


__all__ = ("parse_guest_save_character",)

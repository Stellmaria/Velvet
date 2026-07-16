from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

PUBLIC_COMMANDS = frozenset({"start", "archive", "gallery", "menu"})
CHARACTER_EDITOR_USER_IDS = frozenset({8179531132})
CHARACTER_EDITOR_COMMANDS = frozenset({"characters", "prompt", "setprompt"})
PROMPT_REPLY_MARKER = "PROMPT_MEDIA:"


def normalize_username(value: str) -> str:
    return value.strip().lstrip("@").casefold()


def command_name(text: str) -> str | None:
    cleaned = text.strip()
    if not cleaned.startswith("/"):
        return None
    command_token = cleaned.split(maxsplit=1)[0][1:]
    return command_token.split("@", maxsplit=1)[0].casefold()


def is_public_command_text(text: str) -> bool:
    command = command_name(text)
    return bool(command and command in PUBLIC_COMMANDS)


def is_owner_mention_text(text: str, bot_username: str) -> bool:
    expected = normalize_username(bot_username)
    cleaned = " ".join(text.split())
    if not expected or not cleaned:
        return False

    escaped = re.escape(expected)
    action = r"(?:save|refadd|refdel|refs?)"
    return bool(
        re.fullmatch(
            rf"(?:"
            rf"@{escaped}\s+/?{action}\s+.+|"
            rf"/?{action}\s+@{escaped}\s+.+|"
            rf"/?{action}\s+.+\s+@{escaped}"
            rf")",
            cleaned,
            re.IGNORECASE,
        )
    )


def is_save_mention_text(text: str, bot_username: str) -> bool:
    return is_owner_mention_text(text, bot_username)


@dataclass(frozen=True, slots=True)
class AccessPolicy:
    allowed_user_ids: frozenset[int]
    allowed_usernames: frozenset[str]

    def allows(self, *, user_id: int | None, username: str | None) -> bool:
        if user_id is not None and user_id in self.allowed_user_ids:
            return True
        normalized = normalize_username(username or "")
        return bool(normalized and normalized in self.allowed_usernames)

    def allows_user(self, user: Any | None) -> bool:
        if user is None:
            return False
        return self.allows(
            user_id=getattr(user, "id", None),
            username=getattr(user, "username", None),
        )


__all__ = (
    "AccessPolicy",
    "CHARACTER_EDITOR_COMMANDS",
    "CHARACTER_EDITOR_USER_IDS",
    "PROMPT_REPLY_MARKER",
    "PUBLIC_COMMANDS",
    "command_name",
    "is_owner_mention_text",
    "is_public_command_text",
    "is_save_mention_text",
    "normalize_username",
)

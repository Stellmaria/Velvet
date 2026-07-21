from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Public access includes archive viewing plus user-facing likes, subscriptions and
# download callbacks. The download handler still enforces channel membership or
# approved-watermark policy before sending any file.
# `/menu` still belongs exclusively to the global owner control panel.
PUBLIC_COMMANDS = frozenset({"start", "archive", "gallery"})
PUBLIC_CALLBACK_ACTIONS = frozenset(
    {
        "categories",
        "universes",
        "stories",
        "menu",
        "open",
        "show",
        "noop",
        "close",
        "back",
        "like",
        "sub",
        "download",
    }
)
PUBLIC_WORKSPACE_CALLBACK_ACTIONS = frozenset(
    {
        "noop",
        "close",
        "publics",
        "publicselect",
        "create",
        "home",
        "visibility",
        "modules",
        "modtoggle",
        "modulehelp",
        "module",
        "taxonomy",
        "categories",
        "universes",
        "stories",
        "addcategory",
        "adduniverse",
        "addstory",
        "krimport",
    }
)
PUBLIC_CALLBACK_PREFIX = "pub:"
WORKSPACE_CALLBACK_PREFIX = "wsp:"

# A configured moderator may maintain character cards and archive metadata. This
# role must never inherit owner-only system, publication, analytics, backup,
# Supervisor, Git, or Codex operations. Real IDs are loaded through Settings.
MODERATOR_USER_IDS: frozenset[int] = frozenset()
MODERATOR_COMMANDS = frozenset({"characters", "prompt", "setprompt"})
MODERATOR_TAG_COMMANDS = frozenset(
    {"aliasadd", "tagadd", "aliases", "tags", "aliasdel", "tagdel"}
)
MODERATOR_CALLBACK_ACTIONS = {
    "adir": frozenset(
        {
            "categories",
            "close",
            "menu",
            "noop",
            "profile",
            "pickcat",
            "setcat",
            "pickuni",
            "setuni",
            "pickstory",
        }
    ),
    "astory": frozenset(
        {
            "noop",
            "page",
            "set",
            "mtoggle",
            "mpage",
            "mclear",
            "mdone",
            "mnoop",
        }
    ),
    "arc": frozenset(
        {
            "open",
            "show",
            "noop",
            "spoiler",
            "prompt",
            "promptremove",
            "del",
            "delok",
            "delno",
            "close",
        }
    ),
    # Kept for compatibility with moderator inventories. Runtime download access
    # is decided by public-archive membership/watermark policy.
    "pub": frozenset({"download"}),
}
MODERATOR_TAG_CALLBACK_ACTIONS = frozenset({"menu", "add", "del", "delok"})
MODERATOR_CALLBACK_PREFIXES = tuple(
    f"{prefix}:" for prefix in MODERATOR_CALLBACK_ACTIONS
)

# Compatibility aliases for older imports. New runtime code uses Settings.
CHARACTER_EDITOR_USER_IDS = MODERATOR_USER_IDS
CHARACTER_EDITOR_COMMANDS = MODERATOR_COMMANDS

OWNER_ONLY_COMMANDS = frozenset(
    {
        "admin",
        "menu",
        "system",
        "health",
        "version",
        "analytics",
        "analyticsmenu",
        "channelstats",
        "stats",
        "promptstats",
        "characterstats",
        "backup",
        "quality",
        "auditarchive",
        "publish",
        "publishing",
        "publications",
        "supervisor",
        "status",
        "logs",
        "restart",
        "update",
        "rollback",
        "codex",
        "codex_status",
        "workspace_grant",
        "workspace_revoke",
    }
)

PROMPT_REPLY_MARKER = "PROMPT_MEDIA:"
CHARACTER_TAG_REPLY_MARKER = "CHARACTER_TAG:"


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


def is_owner_only_command_text(text: str) -> bool:
    command = command_name(text)
    return bool(command and command in OWNER_ONLY_COMMANDS)


def _callback_parts(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    parts = value.split(":", maxsplit=2)
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def is_public_callback_data(value: str | None) -> bool:
    parts = _callback_parts(value)
    if parts is None:
        return False
    prefix, action = parts
    if prefix == "pub":
        return action in PUBLIC_CALLBACK_ACTIONS
    if prefix == "wsp":
        # These callbacks are only admitted to the handler. Database-backed grant,
        # membership, ownership and module checks still decide every mutation.
        return action in PUBLIC_WORKSPACE_CALLBACK_ACTIONS
    return False


def is_moderator_callback_data(value: str | None) -> bool:
    parts = _callback_parts(value)
    if parts is None:
        return False
    prefix, action = parts
    if prefix == "ctag":
        return action in MODERATOR_TAG_CALLBACK_ACTIONS
    return action in MODERATOR_CALLBACK_ACTIONS.get(prefix, frozenset())


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
    moderator_user_ids: frozenset[int] = frozenset()

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
    "CHARACTER_TAG_REPLY_MARKER",
    "MODERATOR_CALLBACK_ACTIONS",
    "MODERATOR_CALLBACK_PREFIXES",
    "MODERATOR_COMMANDS",
    "MODERATOR_TAG_CALLBACK_ACTIONS",
    "MODERATOR_TAG_COMMANDS",
    "MODERATOR_USER_IDS",
    "OWNER_ONLY_COMMANDS",
    "PROMPT_REPLY_MARKER",
    "PUBLIC_CALLBACK_ACTIONS",
    "PUBLIC_CALLBACK_PREFIX",
    "PUBLIC_COMMANDS",
    "PUBLIC_WORKSPACE_CALLBACK_ACTIONS",
    "WORKSPACE_CALLBACK_PREFIX",
    "command_name",
    "is_moderator_callback_data",
    "is_owner_mention_text",
    "is_owner_only_command_text",
    "is_public_callback_data",
    "is_public_command_text",
    "is_save_mention_text",
    "normalize_username",
)

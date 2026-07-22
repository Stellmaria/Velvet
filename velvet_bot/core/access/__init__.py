from velvet_bot.core.access.policy import (
    AccessPolicy,
    CHARACTER_EDITOR_COMMANDS,
    CHARACTER_EDITOR_USER_IDS,
    CHARACTER_TAG_REPLY_MARKER,
    MODERATOR_CALLBACK_ACTIONS,
    MODERATOR_CALLBACK_PREFIXES,
    MODERATOR_COMMANDS,
    MODERATOR_TAG_CALLBACK_ACTIONS,
    MODERATOR_TAG_COMMANDS,
    MODERATOR_USER_IDS,
    OWNER_ONLY_COMMANDS,
    PROMPT_REPLY_MARKER,
    PUBLIC_CALLBACK_ACTIONS,
    PUBLIC_CALLBACK_PREFIX,
    PUBLIC_COMMANDS,
    WORKSPACE_MEMBER_CALLBACK_PREFIXES as _BASE_WORKSPACE_MEMBER_CALLBACK_PREFIXES,
    WORKSPACE_MEMBER_COMMANDS as _BASE_WORKSPACE_MEMBER_COMMANDS,
    command_name,
    is_moderator_callback_data,
    is_owner_mention_text,
    is_owner_only_command_text,
    is_public_callback_data,
    is_public_command_text,
    is_save_mention_text,
    normalize_username,
)

# Personal workspace owners must be able to reach their own setup and lifecycle
# routes without being mistaken for global bot owners.
WORKSPACE_MEMBER_COMMANDS = _BASE_WORKSPACE_MEMBER_COMMANDS | frozenset(
    {
        "workspace_setup",
        "workspace_guide",
        "workspace_setup_status",
        "workspace_bind",
        "workspace_bind_channel",
        "workspace_unbind",
        "workspace_delete",
    }
)
WORKSPACE_MEMBER_CALLBACK_PREFIXES = (
    *_BASE_WORKSPACE_MEMBER_CALLBACK_PREFIXES,
    "wob:",
    "wpa:",
    "wref:",
)


def is_workspace_member_command_text(text: str) -> bool:
    command = command_name(text)
    return bool(command and command in WORKSPACE_MEMBER_COMMANDS)


def is_workspace_member_callback_data(value: str | None) -> bool:
    return bool(
        value
        and any(
            value.startswith(prefix)
            for prefix in WORKSPACE_MEMBER_CALLBACK_PREFIXES
        )
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
    "WORKSPACE_MEMBER_CALLBACK_PREFIXES",
    "WORKSPACE_MEMBER_COMMANDS",
    "command_name",
    "is_moderator_callback_data",
    "is_owner_mention_text",
    "is_owner_only_command_text",
    "is_public_callback_data",
    "is_public_command_text",
    "is_save_mention_text",
    "is_workspace_member_callback_data",
    "is_workspace_member_command_text",
    "normalize_username",
)

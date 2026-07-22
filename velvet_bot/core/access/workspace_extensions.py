from __future__ import annotations

from velvet_bot.core.access import policy

_EXTRA_WORKSPACE_COMMANDS = frozenset(
    {
        "workspace_setup",
        "workspace_guide",
        "workspace_setup_status",
        "workspace_bind",
        "workspace_bind_channel",
        "workspace_unbind",
        "workspace_quick_setup",
        "workspace_delete",
    }
)
_EXTRA_WORKSPACE_CALLBACK_PREFIXES = ("wob:", "wqs:", "wsdel:")


def install_workspace_access_extensions() -> None:
    """Register personal-workspace onboarding routes before polling starts."""

    policy.WORKSPACE_MEMBER_COMMANDS = frozenset(
        set(policy.WORKSPACE_MEMBER_COMMANDS) | set(_EXTRA_WORKSPACE_COMMANDS)
    )
    policy.WORKSPACE_MEMBER_CALLBACK_PREFIXES = tuple(
        dict.fromkeys(
            (*policy.WORKSPACE_MEMBER_CALLBACK_PREFIXES, *_EXTRA_WORKSPACE_CALLBACK_PREFIXES)
        )
    )


__all__ = ("install_workspace_access_extensions",)

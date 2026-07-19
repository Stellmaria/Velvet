from __future__ import annotations

from aiogram.types import User

from velvet_bot.access import AccessPolicy


def has_public_manager_access(
    user: User | None,
    access_policy: AccessPolicy,
) -> bool:
    """Allow configured moderators and every configured bot owner."""
    return bool(
        user
        and (
  access_policy.allows_moderator_user(user)
  or access_policy.allows_user(user)
        )
    )

from __future__ import annotations

from aiogram.types import User

from velvet_bot.access import AccessPolicy
from velvet_bot.public_ui import PUBLIC_DOWNLOAD_USER_ID


def has_public_manager_access(
    user: User | None,
    access_policy: AccessPolicy,
) -> bool:
    """Allow the dedicated editor and every configured bot owner."""
    if user is None:
        return False
    return user.id == PUBLIC_DOWNLOAD_USER_ID or access_policy.allows_user(user)

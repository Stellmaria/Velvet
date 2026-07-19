from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

ADULT_CHANNEL_ID = -1003807972037

logger = logging.getLogger(__name__)


async def has_adult_channel_access(bot: Bot, user_id: int) -> bool:
    """Return whether the user currently belongs to the configured +18 channel."""
    try:
        member = await bot.get_chat_member(
            chat_id=ADULT_CHANNEL_ID,
            user_id=int(user_id),
        )
    except TelegramAPIError:
        logger.exception(
            "Failed to check +18 channel membership channel=%s user=%s",
            ADULT_CHANNEL_ID,
            user_id,
        )
        return False

    status_value = getattr(member.status, "value", member.status)
    status = str(status_value)
    return status in {"creator", "administrator", "member"} or bool(
        getattr(member, "is_member", False)
    )


__all__ = ("ADULT_CHANNEL_ID", "has_adult_channel_access")

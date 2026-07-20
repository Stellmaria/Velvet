from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

from velvet_bot.core.config.settings import DEFAULT_ADULT_CHANNEL_ID

logger = logging.getLogger(__name__)


async def has_adult_channel_access(
    bot: Bot,
    user_id: int,
    *,
    channel_id: int = DEFAULT_ADULT_CHANNEL_ID,
) -> bool:
    """Return whether the user currently belongs to the configured +18 channel."""
    try:
        member = await bot.get_chat_member(
            chat_id=int(channel_id),
            user_id=int(user_id),
        )
    except TelegramBadRequest as error:
        if "chat not found" in str(error).casefold():
            logger.info(
                "+18 channel is unavailable; membership check denied channel=%s user=%s",
                channel_id,
                user_id,
            )
            return False
        logger.exception(
            "Failed to check +18 channel membership channel=%s user=%s",
            channel_id,
            user_id,
        )
        return False
    except TelegramAPIError:
        logger.exception(
            "Failed to check +18 channel membership channel=%s user=%s",
            channel_id,
            user_id,
        )
        return False

    status_value = getattr(member.status, "value", member.status)
    status = str(status_value)
    return status in {"creator", "administrator", "member"} or bool(
        getattr(member, "is_member", False)
    )


__all__ = ("has_adult_channel_access",)

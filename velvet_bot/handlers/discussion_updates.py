from __future__ import annotations

from collections import Counter
from typing import Any

from aiogram import Router
from aiogram.types import (
    Message,
    MessageReactionCountUpdated,
    MessageReactionUpdated,
)

from velvet_bot.analytics_reactions import set_analytics_reaction_counts
from velvet_bot.database import Database
from velvet_bot.discussion_analytics import apply_discussion_reaction_delta

router = Router(name=__name__)


def reaction_key(reaction: Any) -> str:
    emoji = getattr(reaction, "emoji", None)
    if emoji:
        return str(emoji)
    custom_emoji_id = getattr(reaction, "custom_emoji_id", None)
    if custom_emoji_id:
        return f"custom:{custom_emoji_id}"
    name = type(reaction).__name__.casefold()
    return "paid" if "paid" in name else name


@router.edited_message()
async def handle_edited_discussion_passthrough(message: Message) -> None:
    """The analytics middleware stores the edit before this no-op handler runs."""
    return None


@router.message_reaction()
async def handle_discussion_reaction_delta(
    update: MessageReactionUpdated,
    database: Database,
) -> None:
    old = Counter(reaction_key(item) for item in update.old_reaction)
    new = Counter(reaction_key(item) for item in update.new_reaction)
    delta = {
        key: new.get(key, 0) - old.get(key, 0)
        for key in old.keys() | new.keys()
        if new.get(key, 0) != old.get(key, 0)
    }
    if delta:
        await apply_discussion_reaction_delta(
            database,
            chat_id=update.chat.id,
            message_id=update.message_id,
            delta=delta,
        )


@router.message_reaction_count()
async def handle_analytics_reaction_count(
    update: MessageReactionCountUpdated,
    database: Database,
) -> None:
    breakdown = {
        reaction_key(item.type): int(item.total_count)
        for item in update.reactions
        if int(item.total_count) > 0
    }
    await set_analytics_reaction_counts(
        database,
        chat_id=update.chat.id,
        message_id=update.message_id,
        breakdown=breakdown,
    )

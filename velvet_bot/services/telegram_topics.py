from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ChatMemberStatus

from velvet_bot.topics import TopicReference


async def validate_topic_access(bot: Bot, topic: TopicReference) -> None:
    chat = await bot.get_chat(topic.chat_id)
    if not chat.is_forum:
        raise ValueError("Ссылка должна вести в тему группы с включёнными ветками.")
    bot_info = await bot.get_me()
    member = await bot.get_chat_member(topic.chat_id, bot_info.id)
    if member.status not in {
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
    }:
        raise ValueError(
            "Бот должен быть администратором группы, к теме которой привязывается персонаж."
        )


__all__ = ("validate_topic_access",)

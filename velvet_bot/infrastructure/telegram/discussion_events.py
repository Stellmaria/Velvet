from __future__ import annotations

from aiogram.types import Message, MessageOriginChannel

from velvet_bot.channel_analytics import detect_media_type
from velvet_bot.domains.discussions.models import DiscussionMessageEvent


def discussion_event_from_message(message: Message) -> DiscussionMessageEvent:
    sender_is_bot = bool(message.from_user and message.from_user.is_bot)
    if message.from_user is not None:
        sender_id = f"user{message.from_user.id}"
        sender_name = message.from_user.full_name
    elif message.sender_chat is not None:
        sender_id = f"chat{message.sender_chat.id}"
        sender_name = message.sender_chat.title or message.sender_chat.username
    else:
        sender_id = None
        sender_name = None

    forward_channel_id: int | None = None
    forward_message_id: int | None = None
    if isinstance(message.forward_origin, MessageOriginChannel):
        forward_channel_id = int(message.forward_origin.chat.id)
        forward_message_id = int(message.forward_origin.message_id)
    else:
        legacy_chat = getattr(message, "forward_from_chat", None)
        legacy_message_id = getattr(message, "forward_from_message_id", None)
        if legacy_chat is not None and legacy_message_id is not None:
            forward_channel_id = int(legacy_chat.id)
            forward_message_id = int(legacy_message_id)

    reply = message.reply_to_message
    return DiscussionMessageEvent(
        chat_id=int(message.chat.id),
        chat_title=message.chat.title,
        chat_username=message.chat.username,
        message_id=int(message.message_id),
        posted_at=message.date,
        edited_at=message.edit_date,
        sender_is_bot=sender_is_bot,
        sender_id=sender_id,
        sender_name=sender_name,
        text_content=message.text or message.caption or "",
        media_group_id=(str(message.media_group_id) if message.media_group_id else None),
        media_type=detect_media_type(message),
        has_spoiler=bool(getattr(message, "has_media_spoiler", False)),
        reply_to_message_id=(int(reply.message_id) if reply is not None else None),
        reply_text=(reply.text or reply.caption or "") if reply is not None else "",
        reply_date=reply.date if reply is not None else None,
        reply_is_automatic_forward=(
            bool(getattr(reply, "is_automatic_forward", False))
            if reply is not None
            else False
        ),
        topic_id=getattr(message, "message_thread_id", None),
        is_automatic_forward=bool(getattr(message, "is_automatic_forward", False)),
        forward_channel_id=forward_channel_id,
        forward_message_id=forward_message_id,
    )


__all__ = ("discussion_event_from_message",)

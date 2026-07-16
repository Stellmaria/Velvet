from __future__ import annotations

from aiogram.types import Message
from aiogram.types.message_origin_channel import MessageOriginChannel

from velvet_bot.domains.discussions.models import DiscussionMessageEvent
from velvet_bot.media import extract_media


def _message_sender(message: Message) -> tuple[str | None, str | None]:
    if message.from_user is not None:
        sender_id = f"user:{message.from_user.id}"
        sender_name = message.from_user.full_name
        if message.from_user.username:
            sender_name = f"{sender_name} (@{message.from_user.username})"
        return sender_id, sender_name
    if message.sender_chat is not None:
        sender_id = f"chat:{message.sender_chat.id}"
        sender_name = message.sender_chat.title or message.sender_chat.username
        return sender_id, sender_name
    return None, None


def discussion_event_from_message(message: Message) -> DiscussionMessageEvent:
    media = extract_media(message)
    sender_id, sender_name = _message_sender(message)
    forward_channel_id: int | None = None
    forward_message_id: int | None = None
    if isinstance(message.forward_origin, MessageOriginChannel):
        forward_channel_id = int(message.forward_origin.chat.id)
        forward_message_id = int(message.forward_origin.message_id)

    return DiscussionMessageEvent(
        discussion_chat_id=int(message.chat.id),
        message_id=int(message.message_id),
        posted_at=message.date,
        edited_at=message.edit_date,
        sender_id=sender_id,
        sender_name=sender_name,
        text_content=message.text or message.caption or "",
        media_group_id=(str(message.media_group_id) if message.media_group_id else None),
        media_type=(media.media_type if media else "text"),
        telegram_file_id=(media.telegram_file_id if media else None),
        telegram_file_unique_id=(media.telegram_file_unique_id if media else None),
        file_size=(media.file_size if media else None),
        mime_type=(media.mime_type if media else None),
        original_file_name=(media.original_file_name if media else None),
        has_spoiler=bool(getattr(message, "has_media_spoiler", False)),
        reply_to_message_id=(
            int(message.reply_to_message.message_id)
            if message.reply_to_message is not None
            else None
        ),
        is_automatic_forward=bool(message.is_automatic_forward),
        forward_channel_id=forward_channel_id,
        forward_message_id=forward_message_id,
    )


__all__ = ("discussion_event_from_message",)

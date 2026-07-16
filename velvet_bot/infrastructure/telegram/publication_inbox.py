from __future__ import annotations

from aiogram.types import Message

from velvet_bot.domains.publication.models import PublicationInboxPayload
from velvet_bot.media import extract_media


def publication_payload_from_message(
    message: Message,
    *,
    owner_id: int,
) -> PublicationInboxPayload:
    media = extract_media(message)
    return PublicationInboxPayload(
        owner_id=int(owner_id),
        source_chat_id=int(message.chat.id),
        source_message_id=int(message.message_id),
        media_group_id=(str(message.media_group_id) if message.media_group_id else None),
        text_content=message.text or message.caption or "",
        telegram_file_id=(media.telegram_file_id if media else None),
        telegram_file_unique_id=(media.telegram_file_unique_id if media else None),
        media_type=(media.media_type if media else "text"),
        mime_type=(media.mime_type if media else None),
        file_name=(media.original_file_name if media else None),
        file_size=(media.file_size if media else None),
        has_spoiler=bool(getattr(message, "has_media_spoiler", False)),
    )


__all__ = ("publication_payload_from_message",)

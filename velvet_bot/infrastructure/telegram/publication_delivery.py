from __future__ import annotations

from aiogram import Bot
from aiogram.types import (
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)

from velvet_bot.domains.publication.constants import CAPTION_LIMIT, TEXT_LIMIT
from velvet_bot.domains.publication.models import PublicationDraft, PublicationItem


def split_publication_text(text: str, *, limit: int = TEXT_LIMIT) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    chunks: list[str] = []
    remaining = cleaned
    while len(remaining) > limit:
        boundary = remaining.rfind("\n", 0, limit + 1)
        if boundary < limit // 2:
            boundary = remaining.rfind(" ", 0, limit + 1)
        if boundary < limit // 2:
            boundary = limit
        chunks.append(remaining[:boundary].rstrip())
        remaining = remaining[boundary:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


class TelegramPublicationDelivery:
    """Deliver a validated publication draft through Telegram Bot API."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send(self, draft: PublicationDraft) -> list[int]:
        sent_ids: list[int] = []
        text = draft.text_content.strip()
        caption = text if draft.items and len(text) <= CAPTION_LIMIT else None

        if text and (not draft.items or caption is None):
            messages = await self._send_text(draft.target_chat_id, text)
            sent_ids.extend(message.message_id for message in messages)

        if not draft.items:
            return sent_ids
        if len(draft.items) == 1:
            message = await self._send_single_media(
                draft,
                draft.items[0],
                caption=caption,
            )
            sent_ids.append(message.message_id)
            return sent_ids

        messages = await self._bot.send_media_group(
            chat_id=draft.target_chat_id,
            media=self._album_media(draft, caption),
        )
        sent_ids.extend(message.message_id for message in messages)
        return sent_ids

    async def _send_text(self, chat_id: int, text: str) -> list[Message]:
        messages: list[Message] = []
        for chunk in split_publication_text(text):
            messages.append(
                await self._bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode=None,
                    disable_web_page_preview=False,
                )
            )
        return messages

    async def _send_single_media(
        self,
        draft: PublicationDraft,
        item: PublicationItem,
        *,
        caption: str | None,
    ) -> Message:
        common = {
            "chat_id": draft.target_chat_id,
            "caption": caption,
            "parse_mode": None,
        }
        spoiler = draft.has_spoiler or item.has_spoiler
        if item.media_type == "photo":
            return await self._bot.send_photo(
                photo=item.telegram_file_id,
                has_spoiler=spoiler,
                **common,
            )
        if item.media_type == "video":
            return await self._bot.send_video(
                video=item.telegram_file_id,
                has_spoiler=spoiler,
                **common,
            )
        if item.media_type == "animation":
            return await self._bot.send_animation(
                animation=item.telegram_file_id,
                has_spoiler=spoiler,
                **common,
            )
        return await self._bot.send_document(document=item.telegram_file_id, **common)

    @staticmethod
    def _album_media(draft: PublicationDraft, caption: str | None):
        result = []
        for index, item in enumerate(draft.items):
            item_caption = caption if index == 0 else None
            spoiler = draft.has_spoiler or item.has_spoiler
            if item.media_type == "photo":
                result.append(
                    InputMediaPhoto(
                        media=item.telegram_file_id,
                        caption=item_caption,
                        parse_mode=None,
                        has_spoiler=spoiler,
                    )
                )
            elif item.media_type == "video":
                result.append(
                    InputMediaVideo(
                        media=item.telegram_file_id,
                        caption=item_caption,
                        parse_mode=None,
                        has_spoiler=spoiler,
                    )
                )
            elif item.media_type == "document":
                result.append(
                    InputMediaDocument(
                        media=item.telegram_file_id,
                        caption=item_caption,
                        parse_mode=None,
                    )
                )
            else:
                raise ValueError(f"Тип {item.media_type} нельзя отправить в альбоме.")
        return result


__all__ = ("TelegramPublicationDelivery", "split_publication_text")

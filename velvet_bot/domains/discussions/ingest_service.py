from __future__ import annotations

from velvet_bot.channel_analytics import analyze_prompt_text, extract_hashtags, extract_links
from velvet_bot.domains.discussions.ingest_repository import DiscussionIngestRepository
from velvet_bot.domains.discussions.models import (
    DiscussionIngestResult,
    DiscussionMessageEvent,
)


class DiscussionIngestService:
    """Classify and persist neutral live discussion events."""

    def __init__(self, repository: DiscussionIngestRepository) -> None:
        self._repository = repository

    async def ingest(self, event: DiscussionMessageEvent) -> DiscussionIngestResult:
        if event.sender_is_bot:
            return DiscussionIngestResult(False, None, None, None)

        parent_channel_id = await self._repository.get_parent_channel_id(event.chat_id)
        if parent_channel_id is None:
            return DiscussionIngestResult(False, None, None, None)

        source_channel_message_id = (
            event.forward_message_id
            if event.forward_channel_id == parent_channel_id
            else None
        )
        is_root = bool(source_channel_message_id is not None or event.is_automatic_forward)
        root_message_id = await self._repository.resolve_root_message_id(
            event,
            is_root=is_root,
        )
        prompt = analyze_prompt_text(event.text_content)
        publication_key = (
            f"live-album:{event.media_group_id}"
            if event.media_group_id
            else f"live-message:{event.message_id}"
        )
        stored = await self._repository.store_message(
            event,
            parent_channel_id=parent_channel_id,
            source_channel_message_id=source_channel_message_id,
            root_message_id=root_message_id,
            is_root=is_root,
            publication_key=publication_key,
            is_prompt=prompt.is_prompt,
            prompt_score=prompt.score,
            has_important=prompt.has_important,
            has_strict=prompt.has_strict,
            has_negative=prompt.has_negative,
            has_technical=prompt.has_technical,
            has_palette=prompt.has_palette,
            hashtags=extract_hashtags(event.text_content),
            links=extract_links(event.text_content),
        )
        return DiscussionIngestResult(
            stored=stored,
            parent_channel_id=parent_channel_id,
            root_message_id=root_message_id,
            source_channel_message_id=source_channel_message_id,
        )


__all__ = ("DiscussionIngestService",)

from __future__ import annotations

from velvet_bot.channel_analytics import analyze_prompt_text, extract_hashtags, extract_links
from velvet_bot.domains.discussions.ingest_repository import DiscussionIngestRepository
from velvet_bot.domains.discussions.models import (
    DiscussionIngestResult,
    DiscussionMessageEvent,
)


class DiscussionIngestService:
    """Classify and persist neutral live discussion message events."""

    def __init__(self, repository: DiscussionIngestRepository) -> None:
        self._repository = repository

    async def ingest(self, event: DiscussionMessageEvent) -> DiscussionIngestResult:
        parent_channel_id = await self._repository.get_parent_channel_id(
            event.discussion_chat_id
        )
        if parent_channel_id is None:
            return DiscussionIngestResult(False, None, None, None)

        root_channel_id: int | None = None
        root_message_id: int | None = None
        if event.is_automatic_forward:
            root_channel_id, root_message_id = (
                await self._repository.match_autoforwarded_post(
                    event=event,
                    parent_channel_id=parent_channel_id,
                )
            )
        elif event.reply_to_message_id is not None:
            root_channel_id, root_message_id = (
                await self._repository.resolve_root_reference(
                    discussion_chat_id=event.discussion_chat_id,
                    message_id=event.reply_to_message_id,
                )
            )

        if root_channel_id is None and root_message_id is None:
            root_channel_id = event.discussion_chat_id
            root_message_id = event.message_id

        hashtags = [display for display, _ in extract_hashtags(event.text_content)]
        prompt = analyze_prompt_text(event.text_content)
        links = extract_links(event.text_content)
        await self._repository.upsert_message(
            event=event,
            parent_channel_id=parent_channel_id,
            root_channel_id=root_channel_id,
            root_message_id=root_message_id,
            hashtags=hashtags,
            is_prompt=prompt.is_prompt,
            links=links,
        )
        return DiscussionIngestResult(
            stored=True,
            parent_channel_id=parent_channel_id,
            root_channel_id=root_channel_id,
            root_message_id=root_message_id,
        )


__all__ = ("DiscussionIngestService",)

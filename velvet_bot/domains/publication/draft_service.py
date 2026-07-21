from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Awaitable, Callable
from datetime import datetime

from velvet_bot.channel_analytics import analyze_prompt_text, extract_hashtags
from velvet_bot.domains.publication.draft_repository import PublicationDraftRepository
from velvet_bot.domains.publication.models import PublicationDraft, PublicationInboxPayload
from velvet_bot.domains.publication.repository import PublicationRepository
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.post_classification import classify_post

DraftValidator = Callable[..., Awaitable[PublicationDraft]]


class PublicationDraftService:
    """Create and edit publication drafts within a workspace boundary."""

    def __init__(
        self,
        *,
        drafts: PublicationRepository,
        commands: PublicationDraftRepository,
        validator: DraftValidator,
    ) -> None:
        self._drafts = drafts
        self._commands = commands
        self._validator = validator

    async def _validate(
        self,
        draft_id: int,
        owner_id: int,
        workspace_id: int,
    ) -> PublicationDraft:
        if int(workspace_id) == DEFAULT_WORKSPACE_ID:
            return await self._validator(draft_id, owner_id)
        return await self._validator(draft_id, owner_id, workspace_id)

    async def capture(self, payload: PublicationInboxPayload) -> None:
        await self._commands.capture_inbox(payload)

    async def create_from_payload(
        self,
        payload: PublicationInboxPayload,
        *,
        target_chat_id: int,
    ) -> PublicationDraft:
        await self.capture(payload)
        items = await self._commands.list_source_items(payload)
        if not items:
            raise ValueError("Сообщение для черновика не найдено.")

        text_parts: list[str] = []
        for item in items:
            value = item.payload.text_content.strip()
            if value and value not in text_parts:
                text_parts.append(value)
        text_content = "\n\n".join(text_parts)
        unique_ids = [
            item.payload.telegram_file_unique_id
            for item in items
            if item.payload.telegram_file_unique_id
        ]
        content_hash = self.content_hash(text_content, unique_ids)
        prompt = analyze_prompt_text(text_content)
        hashtags = extract_hashtags(text_content)
        media_type = next(
            (
                item.payload.media_type
                for item in items
                if item.payload.telegram_file_id
            ),
            "text",
        )
        classification = classify_post(
            text_content,
            hashtags,
            is_prompt=prompt.is_prompt,
            media_type=media_type,
        )
        draft = await self._commands.create_draft(
            source=payload,
            target_chat_id=target_chat_id,
            text_content=text_content,
            post_type=classification.post_type,
            content_hash=content_hash,
            has_spoiler=any(item.payload.has_spoiler for item in items),
            items=items,
        )
        return await self._validate(draft.id, payload.owner_id, payload.workspace_id)

    async def set_spoiler(
        self,
        draft_id: int,
        *,
        owner_id: int,
        enabled: bool,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> PublicationDraft:
        await self._commands.set_spoiler(
            draft_id,
            owner_id=owner_id,
            enabled=enabled,
            workspace_id=workspace_id,
        )
        return await self._validate(draft_id, owner_id, workspace_id)

    async def update_text(
        self,
        draft_id: int,
        *,
        owner_id: int,
        text: str,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> PublicationDraft:
        cleaned = text.strip()
        draft = await self._drafts.get_draft(
            draft_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
        )
        if draft is None:
            raise ValueError("Черновик не найден в выбранном пространстве.")
        content_hash = self.content_hash(
            cleaned,
            [item.telegram_file_unique_id or item.telegram_file_id for item in draft.items],
        )
        await self._commands.update_text(
            draft_id,
            owner_id=owner_id,
            text=cleaned,
            content_hash=content_hash,
            workspace_id=workspace_id,
        )
        return await self._validate(draft_id, owner_id, workspace_id)

    async def schedule(
        self,
        draft_id: int,
        *,
        owner_id: int,
        scheduled_at: datetime,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> PublicationDraft:
        draft = await self._validate(draft_id, owner_id, workspace_id)
        if draft.validation_error_count:
            raise ValueError("Сначала исправьте ошибки проверки.")
        return await self._commands.schedule(
            draft_id,
            owner_id=owner_id,
            scheduled_at=scheduled_at,
            workspace_id=workspace_id,
        )

    async def cancel(
        self,
        draft_id: int,
        *,
        owner_id: int,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> PublicationDraft:
        return await self._commands.cancel(
            draft_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
        )

    async def retry(
        self,
        draft_id: int,
        *,
        owner_id: int,
        workspace_id: int = DEFAULT_WORKSPACE_ID,
    ) -> PublicationDraft:
        await self._commands.retry(
            draft_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
        )
        return await self._validate(draft_id, owner_id, workspace_id)

    @staticmethod
    def content_hash(text: str, unique_ids: list[str]) -> str:
        normalized_text = unicodedata.normalize("NFKC", text).strip()
        payload = "\n".join([normalized_text, *sorted(unique_ids)])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = ("PublicationDraftService",)

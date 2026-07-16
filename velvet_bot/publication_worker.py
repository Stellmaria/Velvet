from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.types import (
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)

from velvet_bot.database import Database
from velvet_bot.publication_workflow import (
    CAPTION_LIMIT,
    TEXT_LIMIT,
    PublicationDraft,
    PublicationItem,
    get_publication_draft,
    validate_publication_draft,
)
from velvet_bot.repositories.publication_repository import PublicationRepository

logger = logging.getLogger(__name__)


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


async def _send_text(bot: Bot, chat_id: int, text: str) -> list[Message]:
    messages: list[Message] = []
    for chunk in split_publication_text(text):
        messages.append(
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=None,
                disable_web_page_preview=False,
            )
        )
    return messages


async def _send_single_media(
    bot: Bot,
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
        return await bot.send_photo(
            photo=item.telegram_file_id,
            has_spoiler=spoiler,
            **common,
        )
    if item.media_type == "video":
        return await bot.send_video(
            video=item.telegram_file_id,
            has_spoiler=spoiler,
            **common,
        )
    if item.media_type == "animation":
        return await bot.send_animation(
            animation=item.telegram_file_id,
            has_spoiler=spoiler,
            **common,
        )
    return await bot.send_document(document=item.telegram_file_id, **common)


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


async def send_publication(bot: Bot, draft: PublicationDraft) -> list[int]:
    sent_ids: list[int] = []
    text = draft.text_content.strip()
    caption = text if draft.items and len(text) <= CAPTION_LIMIT else None

    if text and (not draft.items or caption is None):
        text_messages = await _send_text(bot, draft.target_chat_id, text)
        sent_ids.extend(message.message_id for message in text_messages)

    if not draft.items:
        return sent_ids
    if len(draft.items) == 1:
        message = await _send_single_media(
            bot,
            draft,
            draft.items[0],
            caption=caption,
        )
        sent_ids.append(message.message_id)
        return sent_ids

    messages = await bot.send_media_group(
        chat_id=draft.target_chat_id,
        media=_album_media(draft, caption),
    )
    sent_ids.extend(message.message_id for message in messages)
    return sent_ids


async def publish_publication_draft(
    bot: Bot,
    database: Database,
    draft_id: int,
    *,
    owner_id: int | None = None,
    actor_id: int | None = None,
) -> PublicationDraft:
    repository = PublicationRepository(database)
    draft = await get_publication_draft(database, draft_id, owner_id=owner_id)
    if draft is None:
        raise ValueError("Черновик не найден.")
    if owner_id is not None:
        draft = await validate_publication_draft(database, draft_id, owner_id=owner_id)
    if draft.validation_error_count:
        raise ValueError("Публикация заблокирована ошибками проверки.")
    if draft.status == "published":
        return draft

    if not await repository.claim_for_publishing(draft_id):
        current = await get_publication_draft(database, draft_id, owner_id=owner_id)
        if current is not None and current.status == "published":
            return current
        raise ValueError("Черновик уже обрабатывается или отменён.")

    try:
        refreshed = await get_publication_draft(database, draft_id, owner_id=owner_id)
        if refreshed is None:
            raise RuntimeError("Черновик исчез перед публикацией.")
        message_ids = await send_publication(bot, refreshed)
        await repository.mark_published(
            draft_id,
            message_ids=message_ids,
            actor_id=actor_id,
        )
    except Exception as error:
        logger.exception("Publication failed draft_id=%s", draft_id)
        await repository.mark_error(
            draft_id,
            error=error,
            actor_id=actor_id,
        )
        raise

    result_draft = await get_publication_draft(database, draft_id, owner_id=owner_id)
    if result_draft is None:
        raise RuntimeError("Опубликованный черновик не найден.")
    return result_draft


async def _due_publication_ids(database: Database, *, limit: int = 5) -> list[int]:
    """Backward-compatible queue query delegated to PublicationRepository."""
    return await PublicationRepository(database).list_due_draft_ids(limit=limit)


async def process_due_publications_once(
    bot: Bot,
    database: Database,
    *,
    limit: int = 5,
) -> int:
    """Process one bounded scheduled-publication batch."""
    published = 0
    for draft_id in await _due_publication_ids(database, limit=limit):
        try:
            await publish_publication_draft(
                bot,
                database,
                draft_id,
                actor_id=None,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduled publication failed draft_id=%s", draft_id)
        else:
            published += 1
    return published


async def run_publication_worker(
    bot: Bot,
    database: Database,
    *,
    interval_seconds: float = 15.0,
) -> None:
    """Backward-compatible standalone publication loop."""
    while True:
        try:
            await process_due_publications_once(bot, database)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Publication queue loop failed")
        await asyncio.sleep(interval_seconds)

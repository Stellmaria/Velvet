from __future__ import annotations

import re

from aiogram import Bot, Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, Message

from velvet_bot.database import Database
from velvet_bot.presentation.telegram.routers.publication.center import (
    PublicationCallback,
    handle_check_post,
    handle_publication_callback,
    handle_publication_center,
    handle_publication_reply,
)

router = Router(name=__name__)
_MARKER_RE = re.compile(r"PUBLICATION_(?:SCHEDULE|TEXT):(\d+)")


class PublicationReplyMarkerFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if message.reply_to_message is None:
            return False
        reply_text = (
            message.reply_to_message.text
            or message.reply_to_message.caption
            or ""
        )
        return bool(_MARKER_RE.search(reply_text))


@router.message(Command("publish", "publishing", "publications"))
async def safe_publication_center(message: Message) -> None:
    await handle_publication_center(message)


@router.message(Command("checkpost"))
async def safe_check_post(
    message: Message,
    database: Database,
    analytics_channel_ids: frozenset[int],
    publication_timezone: str = "Europe/Berlin",
) -> None:
    await handle_check_post(
        message,
        database,
        analytics_channel_ids,
        publication_timezone,
    )


@router.callback_query(PublicationCallback.filter())
async def safe_publication_callback(
    callback: CallbackQuery,
    callback_data: PublicationCallback,
    database: Database,
    bot: Bot,
    publication_timezone: str = "Europe/Berlin",
) -> None:
    await handle_publication_callback(
        callback,
        callback_data,
        database,
        bot,
        publication_timezone,
    )


@router.message(PublicationReplyMarkerFilter())
async def safe_publication_reply(
    message: Message,
    database: Database,
    publication_timezone: str = "Europe/Berlin",
) -> None:
    await handle_publication_reply(
        message,
        database,
        publication_timezone,
    )

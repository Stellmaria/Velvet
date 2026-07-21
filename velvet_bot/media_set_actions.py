from __future__ import annotations

import re

import velvet_bot.media_sets as media_sets
from velvet_bot.database import Database
from velvet_bot.domains.media_sets.actions_repository import MediaSetActionsRepository
from velvet_bot.media_sets import CreatedMediaSet

_PROMPT_POST_URL_RE = re.compile(
    r"^https://t\.me/(?:c/\d+|[A-Za-z0-9_]+)/\d+$",
    re.IGNORECASE,
)
_INSTALLED = False


def normalize_prompt_post_url(value: str) -> str:
    normalized = " ".join(str(value).split()).strip()
    if not _PROMPT_POST_URL_RE.fullmatch(normalized):
        raise ValueError(
            "Нужна ссылка на пост Telegram вида https://t.me/channel/123."
        )
    return normalized


async def set_media_set_prompt(
    database: Database,
    *,
    media_set_id: int,
    prompt_post_url: str,
) -> str:
    normalized = normalize_prompt_post_url(prompt_post_url)
    updated = await MediaSetActionsRepository(database).set_prompt_post_url(
        media_set_id=int(media_set_id),
        prompt_post_url=normalized,
    )
    if not updated:
        raise ValueError("Сет больше не найден.")
    return normalized


async def create_media_set_with_prompt(
    database: Database,
    *,
    candidate_id: int,
    created_by: int,
) -> CreatedMediaSet:
    record = await MediaSetActionsRepository(database).create_media_set(
        candidate_id=int(candidate_id),
        created_by=int(created_by),
    )
    return CreatedMediaSet(
        id=record.id,
        title=record.title,
        media_ids=record.media_ids,
        prompt_post_url=record.prompt_post_url,
    )


create_media_set = create_media_set_with_prompt


def install_media_set_actions() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    media_sets.create_media_set = create_media_set_with_prompt
    _INSTALLED = True


install_media_set_actions()

__all__ = (
    "create_media_set",
    "create_media_set_with_prompt",
    "install_media_set_actions",
    "normalize_prompt_post_url",
    "set_media_set_prompt",
)

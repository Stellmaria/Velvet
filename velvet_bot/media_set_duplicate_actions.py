from __future__ import annotations

import velvet_bot.media_sets as media_sets
from velvet_bot.database import Database
from velvet_bot.media_set_duplicate_actions_repository import (
    MediaSetDuplicateActionsRepository,
)

_INSTALLED = False


async def create_set_candidate_from_duplicate(
    database: Database,
    *,
    duplicate_candidate_id: int,
    decided_by: int,
) -> int:
    return await MediaSetDuplicateActionsRepository(
        database
    ).create_set_candidate_from_duplicate(
        duplicate_candidate_id=int(duplicate_candidate_id),
        decided_by=int(decided_by),
    )


def install_media_sets_compatibility() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    media_sets.create_set_candidate_from_duplicate = create_set_candidate_from_duplicate
    _INSTALLED = True


install_media_sets_compatibility()

__all__ = (
    "create_set_candidate_from_duplicate",
    "install_media_sets_compatibility",
)

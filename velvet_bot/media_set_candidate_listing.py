from __future__ import annotations

import velvet_bot.media_sets as media_sets
from velvet_bot.database import Database
from velvet_bot.media_set_candidate_listing_repository import (
    MediaSetCandidateListingRepository,
)
from velvet_bot.media_sets import MediaSetCandidatePage

_INSTALLED = False


async def list_media_set_candidates_by_size(
    database: Database,
    *,
    status: str = "pending",
    page: int = 0,
    page_size: int = 6,
) -> MediaSetCandidatePage:
    id_page = await MediaSetCandidateListingRepository(database).list_ids(
        status=status,
        page=page,
        page_size=page_size,
    )
    candidates = []
    for candidate_id in id_page.ids:
        candidate = await media_sets.get_media_set_candidate(database, candidate_id)
        if candidate is not None and len(candidate.items) >= 2:
            candidates.append(candidate)
    return MediaSetCandidatePage(
        items=tuple(candidates),
        page=id_page.page,
        page_size=id_page.page_size,
        total_items=id_page.total_items,
    )


def install_media_set_candidate_listing() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    media_sets.list_media_set_candidates = list_media_set_candidates_by_size
    _INSTALLED = True


install_media_set_candidate_listing()


__all__ = (
    "install_media_set_candidate_listing",
    "list_media_set_candidates_by_size",
)

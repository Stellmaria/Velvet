from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import velvet_bot.media_set_candidate_listing as listing
import velvet_bot.media_sets as media_sets
from velvet_bot.media_set_candidate_listing_repository import (
    MediaSetCandidateListingRepository,
)
from velvet_bot.media_sets import MediaSetCandidate, MediaSetCandidateItem


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False


def _candidate(candidate_id: int, item_count: int) -> MediaSetCandidate:
    return MediaSetCandidate(
        id=candidate_id,
        suggested_title=f"Сет {candidate_id}",
        reason="Qwen-контекст",
        score=90,
        prompt_post_url=None,
        status="pending",
        items=tuple(
            MediaSetCandidateItem(
                media_id=candidate_id * 100 + index,
                telegram_file_id=f"file-{candidate_id}-{index}",
                media_type="photo",
                file_name=f"image-{candidate_id}-{index}.jpg",
                characters=(f"Персонаж {index}",),
                selected=True,
                context_score=90,
                reason="Общая тема",
            )
            for index in range(item_count)
        ),
    )


class MediaSetCandidateListingTests(unittest.IsolatedAsyncioTestCase):
    async def test_repository_orders_by_item_count_before_score(self) -> None:
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=2),
            fetch=AsyncMock(return_value=[{"id": 9}, {"id": 3}]),
        )
        database = SimpleNamespace(
            acquire=Mock(return_value=_AsyncContext(connection))
        )

        page = await MediaSetCandidateListingRepository(database).list_ids(
            status="pending",
            page=0,
            page_size=6,
        )

        self.assertEqual(page.ids, (9, 3))
        listing_sql = connection.fetch.await_args.args[0]
        self.assertIn("COUNT(*) AS available_item_count", listing_sql)
        self.assertIn(
            "ORDER BY available_item_count DESC, candidate.score DESC",
            listing_sql,
        )
        self.assertIn("HAVING COUNT(*) >= 2", listing_sql)

    async def test_service_keeps_repository_order_and_filters_broken_candidate(self) -> None:
        id_page = SimpleNamespace(
            ids=(9, 3, 1),
            page=0,
            page_size=6,
            total_items=3,
        )
        repository = SimpleNamespace(list_ids=AsyncMock(return_value=id_page))
        candidates = {
            9: _candidate(9, 5),
            3: _candidate(3, 3),
            1: _candidate(1, 1),
        }

        async def get_candidate(database, candidate_id):
            return candidates[candidate_id]

        with (
            patch.object(
                listing,
                "MediaSetCandidateListingRepository",
                new=Mock(return_value=repository),
            ),
            patch.object(
                media_sets,
                "get_media_set_candidate",
                new=AsyncMock(side_effect=get_candidate),
            ),
        ):
            page = await listing.list_media_set_candidates_by_size(
                object(),
                status="pending",
                page=0,
            )

        self.assertEqual([candidate.id for candidate in page.items], [9, 3])
        self.assertEqual(page.total_items, 3)
        repository.list_ids.assert_awaited_once_with(
            status="pending",
            page=0,
            page_size=6,
        )

    def test_installer_replaces_public_listing_once(self) -> None:
        original_installed = listing._INSTALLED
        original_list = media_sets.list_media_set_candidates
        try:
            listing._INSTALLED = False
            media_sets.list_media_set_candidates = Mock()
            listing.install_media_set_candidate_listing()
            first = media_sets.list_media_set_candidates
            listing.install_media_set_candidate_listing()
            self.assertIs(first, media_sets.list_media_set_candidates)
            self.assertIs(first, listing.list_media_set_candidates_by_size)
        finally:
            listing._INSTALLED = original_installed
            media_sets.list_media_set_candidates = original_list


if __name__ == "__main__":
    unittest.main()

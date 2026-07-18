from __future__ import annotations

import asyncio
import inspect
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.publication.models import PublicationDraft
from velvet_bot.domains.publication.service import PublicationService


def _draft(draft_id: int = 1) -> PublicationDraft:
    now = datetime.now(timezone.utc)
    return PublicationDraft(
        id=draft_id,
        owner_id=7,
        target_chat_id=-1001,
        source_chat_id=None,
        source_message_id=None,
        source_media_group_id=None,
        text_content="test",
        status="checked",
        post_type="prompt",
        has_spoiler=False,
        content_hash="hash",
        validation_status="valid",
        validation_error_count=0,
        validation_warning_count=0,
        validation_report=(),
        scheduled_at=None,
        published_at=None,
        published_message_ids=(),
        attempt_count=0,
        last_error=None,
        created_at=now,
        updated_at=now,
        items=(),
    )


class PublicationBroadBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_boundaries_are_explicitly_marked(self) -> None:
        source = inspect.getsource(PublicationService)
        self.assertEqual(2, source.count("p2-approved-boundary:"))
        self.assertIn("compensate-claimed-publication", source)
        self.assertIn("isolate-scheduled-draft", source)

    async def test_delivery_failure_marks_claimed_draft_error_and_reraises(self) -> None:
        draft = _draft()
        repository = SimpleNamespace(
            get_draft=AsyncMock(side_effect=[draft, draft]),
            claim_for_publishing=AsyncMock(return_value=True),
            mark_published=AsyncMock(),
            mark_error=AsyncMock(),
        )
        delivery = SimpleNamespace(send=AsyncMock(side_effect=RuntimeError("send failed")))
        service = PublicationService(
            repository=repository,
            delivery=delivery,
            validator=AsyncMock(),
        )

        with self.assertRaisesRegex(RuntimeError, "send failed"):
            await service.publish(1)

        repository.mark_error.assert_awaited_once()
        repository.mark_published.assert_not_awaited()

    async def test_mark_published_failure_is_compensated_and_reraised(self) -> None:
        draft = _draft()
        repository = SimpleNamespace(
            get_draft=AsyncMock(side_effect=[draft, draft]),
            claim_for_publishing=AsyncMock(return_value=True),
            mark_published=AsyncMock(side_effect=RuntimeError("commit failed")),
            mark_error=AsyncMock(),
        )
        delivery = SimpleNamespace(send=AsyncMock(return_value=[11]))
        service = PublicationService(
            repository=repository,
            delivery=delivery,
            validator=AsyncMock(),
        )

        with self.assertRaisesRegex(RuntimeError, "commit failed"):
            await service.publish(1)

        repository.mark_error.assert_awaited_once()

    async def test_scheduled_failure_is_isolated_and_later_draft_continues(self) -> None:
        repository = SimpleNamespace(
            list_due_draft_ids=AsyncMock(return_value=[1, 2]),
        )
        service = PublicationService(
            repository=repository,
            delivery=SimpleNamespace(),
            validator=AsyncMock(),
        )
        service.publish = AsyncMock(side_effect=[RuntimeError("first"), _draft(2)])

        published = await service.process_due_once(limit=5)

        self.assertEqual(1, published)
        self.assertEqual(2, service.publish.await_count)

    async def test_scheduled_cancellation_is_not_isolated(self) -> None:
        repository = SimpleNamespace(
            list_due_draft_ids=AsyncMock(return_value=[1]),
        )
        service = PublicationService(
            repository=repository,
            delivery=SimpleNamespace(),
            validator=AsyncMock(),
        )
        service.publish = AsyncMock(side_effect=asyncio.CancelledError())

        with self.assertRaises(asyncio.CancelledError):
            await service.process_due_once()


if __name__ == "__main__":
    unittest.main()

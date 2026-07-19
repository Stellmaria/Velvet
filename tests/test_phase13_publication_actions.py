from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.application.publication_actions import PublicationActions


ROOT = Path(__file__).resolve().parents[1]


class PublicationActionsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.drafts = SimpleNamespace(
            get_draft=AsyncMock(return_value="draft"),
            list_drafts=AsyncMock(return_value="page"),
        )
        self.commands = SimpleNamespace(
            set_spoiler=AsyncMock(return_value="spoiler"),
            update_text=AsyncMock(return_value="text"),
            schedule=AsyncMock(return_value="scheduled"),
            cancel=AsyncMock(return_value="cancelled"),
            retry=AsyncMock(return_value="retry"),
        )
        self.validation = SimpleNamespace(validate=AsyncMock(return_value="checked"))
        self.actions = PublicationActions(
            drafts=self.drafts,
            commands=self.commands,
            validation=self.validation,
        )

    async def test_reads_are_delegated(self) -> None:
        self.assertEqual(
            await self.actions.get_draft(12, owner_id=5),
            "draft",
        )
        self.assertEqual(
            await self.actions.list_drafts(
                owner_id=5,
                statuses=("draft", "checked"),
                page=2,
            ),
            "page",
        )
        self.drafts.get_draft.assert_awaited_once_with(12, owner_id=5)
        self.drafts.list_drafts.assert_awaited_once_with(
            owner_id=5,
            statuses=("draft", "checked"),
            page=2,
            page_size=6,
        )

    async def test_commands_are_delegated(self) -> None:
        when = datetime(2026, 7, 18, 20, 30, tzinfo=timezone.utc)
        self.assertEqual(await self.actions.recheck(1, owner_id=5), "checked")
        self.assertEqual(
            await self.actions.set_spoiler(1, owner_id=5, enabled=True),
            "spoiler",
        )
        self.assertEqual(
            await self.actions.update_text(1, owner_id=5, text="new"),
            "text",
        )
        self.assertEqual(
            await self.actions.schedule(1, owner_id=5, scheduled_at=when),
            "scheduled",
        )
        self.assertEqual(await self.actions.cancel(1, owner_id=5), "cancelled")
        self.assertEqual(await self.actions.retry(1, owner_id=5), "retry")

        self.validation.validate.assert_awaited_once_with(1, owner_id=5)
        self.commands.set_spoiler.assert_awaited_once_with(
            1, owner_id=5, enabled=True
        )
        self.commands.update_text.assert_awaited_once_with(
            1, owner_id=5, text="new"
        )
        self.commands.schedule.assert_awaited_once_with(
            1, owner_id=5, scheduled_at=when
        )
        self.commands.cancel.assert_awaited_once_with(1, owner_id=5)
        self.commands.retry.assert_awaited_once_with(1, owner_id=5)

    def test_publication_handler_uses_application_actions(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/publication/center.py"
        ).read_text(encoding="utf-8")
        application_source = (
            ROOT / "velvet_bot/application/publication_actions.py"
        ).read_text(encoding="utf-8")
        self.assertIn("build_publication_actions", source)
        self.assertNotIn("from velvet_bot.publication_workflow", source)
        self.assertNotIn("from velvet_bot.publication_worker", source)
        self.assertNotIn("aiogram", application_source)


if __name__ == "__main__":
    unittest.main()

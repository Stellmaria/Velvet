from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.domains.media_rework.manual import request_manual_rework


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class PublicArchiveReworkContractTests(unittest.TestCase):
    def test_manager_card_exposes_rework_button_and_registration(self) -> None:
        ui = Path("velvet_bot/public_manager_ui.py").read_text(encoding="utf-8")
        bundle = Path(
            "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        handler = Path(
            "velvet_bot/presentation/telegram/public_archive_rework.py"
        ).read_text(encoding="utf-8")

        self.assertIn("🛠 Отправить на доработку", ui)
        self.assertIn('manager_callback("prework"', ui)
        self.assertIn("register_public_archive_rework(router)", bundle)
        self.assertIn('F.action == "prework"', handler)
        self.assertIn("request_manual_rework", handler)


class ManualReworkRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_manual_request_creates_item_and_event(self) -> None:
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=True),
            fetchrow=AsyncMock(return_value=None),
            execute=AsyncMock(),
            transaction=lambda: _AsyncContext(None),
        )
        database = SimpleNamespace(acquire=lambda: _AsyncContext(connection))

        changed = await request_manual_rework(
            database,
            media_id=77,
            user_id=7221553045,
            workspace_id=9,
        )

        self.assertTrue(changed)
        self.assertEqual(3, connection.execute.await_count)
        hide_sql = connection.execute.await_args_list[0].args[0]
        item_sql = connection.execute.await_args_list[1].args[0]
        event_sql = connection.execute.await_args_list[2].args[0]
        self.assertIn("SET is_public = FALSE", hide_sql)
        self.assertIn("character.workspace_id = $2::BIGINT", hide_sql)
        self.assertIn("INSERT INTO media_rework_items", item_sql)
        self.assertIn("workspace_id", item_sql)
        self.assertIn("INSERT INTO media_rework_events", event_sql)
        self.assertIn("workspace_id", event_sql)

    async def test_repeated_active_admin_request_is_idempotent(self) -> None:
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=True),
            fetchrow=AsyncMock(
                return_value={"status": "needs_fix", "source": "admin"}
            ),
            execute=AsyncMock(),
            transaction=lambda: _AsyncContext(None),
        )
        database = SimpleNamespace(acquire=lambda: _AsyncContext(connection))

        changed = await request_manual_rework(
            database,
            media_id=77,
            user_id=7221553045,
            workspace_id=9,
        )

        self.assertFalse(changed)
        connection.execute.assert_awaited_once()
        self.assertIn(
            "SET is_public = FALSE",
            connection.execute.await_args.args[0],
        )

    async def test_request_rejects_media_outside_workspace(self) -> None:
        connection = SimpleNamespace(
            fetchval=AsyncMock(return_value=None),
            fetchrow=AsyncMock(),
            execute=AsyncMock(),
            transaction=lambda: _AsyncContext(None),
        )
        database = SimpleNamespace(acquire=lambda: _AsyncContext(connection))

        with self.assertRaisesRegex(ValueError, "не принадлежит"):
            await request_manual_rework(
                database,
                media_id=77,
                user_id=7221553045,
                workspace_id=9,
            )

        connection.fetchrow.assert_not_awaited()
        connection.execute.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

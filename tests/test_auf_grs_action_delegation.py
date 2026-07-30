from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.presentation.telegram.routers import workspace_auf_grs


class AufGrsActionDelegationTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_grs_action_delegates_to_base_handler_once(self) -> None:
        callback = object()
        callback_data = SimpleNamespace(
            action="review",
            workspace_id=7,
            value=None,
        )
        state = object()
        access_policy = object()
        kie_settings = object()
        database = object()
        ai_usage_service = object()
        ai_task_queue_service = object()

        with patch.object(
            workspace_auf_grs,
            "_handle_base_auf_action",
            new_callable=AsyncMock,
        ) as base_handler:
            await workspace_auf_grs.handle_auf_action(
                callback,
                callback_data,
                state,
                access_policy,
                kie_settings,
                database,
                ai_usage_service,
                ai_task_queue_service,
            )

        base_handler.assert_awaited_once_with(
            callback,
            callback_data,
            state,
            access_policy,
            kie_settings,
            database,
            ai_usage_service,
            ai_task_queue_service,
        )


if __name__ == "__main__":
    unittest.main()

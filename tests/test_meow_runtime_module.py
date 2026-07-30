from __future__ import annotations

import os
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import AITaskRequest, build_ai_task_queue_service
from velvet_bot.domains.auf_runtime import (
    AUF_MODULE_KEY,
    AufProvider,
    AufRuntimeAccessError,
    AufRuntimeService,
    AufRuntimeSettings,
    ProviderAufTaskQueueService,
    WorkspaceAufSettings,
)
from velvet_bot.domains.media_generation import KIE_GENERATION_TASK_TYPE
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID
from velvet_bot.domains.workspaces.product_models import (
    DEFAULT_PERSONAL_MODULE_KEYS,
    GLOBAL_WORKSPACE_CREATOR_ID,
    WORKSPACE_MODULE_KEYS,
)
from velvet_bot.presentation.telegram.routers.workspace_auf_runtime import (
    AufRuntimeCallback,
    build_task_cancel_keyboard,
)


class _FakeRepository:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self.runtime = AufRuntimeSettings(
            kie_concurrency_limit=100,
            grs_concurrency_limit=100,
            workspace_default_limit=5,
            workspace_max_limit=20,
            configured=False,
            setup_notice_sent_at=None,
            updated_by_user_id=None,
            updated_at=now,
        )
        self.workspace = WorkspaceAufSettings(
            workspace_id=7,
            concurrency_limit=5,
            updated_by_user_id=None,
            updated_at=now,
        )
        self.visible = True

    async def set_provider_limit(self, *, provider, limit, updated_by_user_id):
        if provider is AufProvider.KIE:
            self.runtime = replace(
                self.runtime,
                kie_concurrency_limit=limit,
                updated_by_user_id=updated_by_user_id,
            )
        return self.runtime

    async def runtime_settings(self):
        return self.runtime

    async def can_use_auf(self, *, workspace_id, user_id, global_owner):
        return global_owner or (workspace_id == 7 and user_id == 77)

    async def workspace_settings(self, workspace_id):
        return self.workspace

    async def set_workspace_limit(self, *, workspace_id, limit, updated_by_user_id):
        self.workspace = WorkspaceAufSettings(
            workspace_id=workspace_id,
            concurrency_limit=limit,
            updated_by_user_id=updated_by_user_id,
            updated_at=self.workspace.updated_at,
        )
        return self.workspace

    async def is_workspace_owner(self, *, workspace_id, user_id):
        return workspace_id == 7 and user_id == 77

    async def module_is_visible(self, *, workspace_id, user_id, module_key):
        return self.visible

    async def set_module_visible(
        self, *, workspace_id, user_id, module_key, is_visible
    ):
        self.visible = is_visible
        return is_visible


class AufRuntimeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_global_limits_are_owner_only_and_bounded(self) -> None:
        service = AufRuntimeService(_FakeRepository())
        with self.assertRaises(AufRuntimeAccessError):
            await service.set_provider_limit(
                actor_user_id=77,
                provider=AufProvider.KIE,
                limit=50,
            )
        with self.assertRaises(ValueError):
            await service.set_provider_limit(
                actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
                provider=AufProvider.KIE,
                limit=101,
            )

    async def test_workspace_owner_can_select_limit_up_to_twenty(self) -> None:
        service = AufRuntimeService(_FakeRepository())
        settings = await service.set_workspace_limit(
            workspace_id=7,
            actor_user_id=77,
            limit=20,
        )
        self.assertEqual(20, settings.concurrency_limit)
        with self.assertRaises(ValueError):
            await service.set_workspace_limit(
                workspace_id=7,
                actor_user_id=77,
                limit=21,
            )

    async def test_visibility_is_personal_and_owner_controlled(self) -> None:
        repository = _FakeRepository()
        service = AufRuntimeService(repository)
        visible = await service.set_module_visible(
            workspace_id=7,
            actor_user_id=77,
            is_visible=False,
        )
        self.assertFalse(visible)
        self.assertFalse(repository.visible)


class AufModuleContractTests(unittest.TestCase):
    def test_auf_is_explicit_module_not_default_personal_grant(self) -> None:
        self.assertIn(AUF_MODULE_KEY, WORKSPACE_MODULE_KEYS)
        self.assertNotIn(AUF_MODULE_KEY, DEFAULT_PERSONAL_MODULE_KEYS)

    def test_cancel_callback_stays_within_telegram_limit(self) -> None:
        task_id = uuid4()
        keyboard = build_task_cancel_keyboard(workspace_id=7, task_id=task_id)
        callback_data = keyboard.inline_keyboard[0][0].callback_data
        self.assertIsNotNone(callback_data)
        self.assertLessEqual(len(callback_data or ""), 64)
        parsed = AufRuntimeCallback.unpack(callback_data or "")
        self.assertEqual("cancel_task", parsed.action)
        self.assertEqual(str(task_id), parsed.value)

    def test_provider_routes_are_disjoint(self) -> None:
        self.assertTrue(
            set(AufProvider.KIE.model_aliases).isdisjoint(
                AufProvider.GRS.model_aliases
            )
        )


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgreSQLAufQueueTests(unittest.IsolatedAsyncioTestCase):
    _WORKSPACE_OWNER_ID = 799_001

    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        self.tasks = build_ai_task_queue_service(database=self.database)
        self.queue = ProviderAufTaskQueueService(
            database=self.database,
            provider=AufProvider.KIE,
        )
        await self._reset()

    async def asyncTearDown(self) -> None:
        await self._reset()
        await self.database.close()

    async def _reset(self) -> None:
        async with self.database.acquire() as connection:
            await connection.execute("DELETE FROM ai_tasks")
            await connection.execute(
                """
                INSERT INTO workspace_meow_settings (
                    workspace_id,
                    concurrency_limit,
                    updated_by_user_id
                )
                VALUES ($1::BIGINT, 5, $2::BIGINT)
                ON CONFLICT (workspace_id) DO UPDATE
                SET concurrency_limit = 5,
                    updated_by_user_id = EXCLUDED.updated_by_user_id,
                    updated_at = NOW()
                """,
                DEFAULT_WORKSPACE_ID,
                GLOBAL_WORKSPACE_CREATOR_ID,
            )

    async def _enqueue(self, *, created_by: int, index: int) -> None:
        await self.tasks.enqueue(
            AITaskRequest(
                scope=AIBudgetScope.VISION,
                task_type=KIE_GENERATION_TASK_TYPE,
                payload={
                    "request": {"model": "seedream_5_pro"},
                    "workspace_id": DEFAULT_WORKSPACE_ID,
                    "user_id": created_by,
                },
                priority=40,
                dedupe_key=f"test:auf-runtime:{created_by}:{index}",
                max_attempts=3,
                created_by=created_by,
                estimated_cost_rub=Decimal("0"),
            )
        )

    async def test_workspace_quota_and_stell_priority_are_enforced(self) -> None:
        for index in range(10):
            await self._enqueue(created_by=self._WORKSPACE_OWNER_ID, index=index)
        for index in range(2):
            await self._enqueue(
                created_by=GLOBAL_WORKSPACE_CREATOR_ID,
                index=index,
            )

        self.assertEqual(7, await self.queue.eligible_count())

        first = await self.queue.claim_next(worker_id="priority-1")
        second = await self.queue.claim_next(worker_id="priority-2")
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None and second is not None
        self.assertEqual(GLOBAL_WORKSPACE_CREATOR_ID, first.created_by)
        self.assertEqual(GLOBAL_WORKSPACE_CREATOR_ID, second.created_by)

        owner_claims = []
        for index in range(5):
            owner_claims.append(
                await self.queue.claim_next(worker_id=f"owner-{index}")
            )
        self.assertTrue(all(task is not None for task in owner_claims))
        self.assertIsNone(await self.queue.claim_next(worker_id="owner-over-limit"))
        self.assertEqual(0, await self.queue.eligible_count())


if __name__ == "__main__":
    unittest.main()

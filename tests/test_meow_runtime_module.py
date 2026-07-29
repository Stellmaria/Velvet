from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from velvet_bot.domains.meow_runtime import (
    MeowProvider,
    MeowRuntimeAccessError,
    MeowRuntimeService,
    MeowRuntimeSettings,
    WorkspaceMeowSettings,
)
from velvet_bot.domains.workspaces.product_models import (
    DEFAULT_PERSONAL_MODULE_KEYS,
    GLOBAL_WORKSPACE_CREATOR_ID,
    WORKSPACE_MODULE_KEYS,
)
from velvet_bot.presentation.telegram.routers.workspace_meow_runtime import (
    MeowRuntimeCallback,
    build_task_cancel_keyboard,
)


class _FakeRepository:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self.runtime = MeowRuntimeSettings(
            kie_concurrency_limit=100,
            grs_concurrency_limit=100,
            workspace_default_limit=5,
            workspace_max_limit=20,
            configured=False,
            setup_notice_sent_at=None,
            updated_by_user_id=None,
            updated_at=now,
        )
        self.workspace = WorkspaceMeowSettings(
            workspace_id=7,
            concurrency_limit=5,
            updated_by_user_id=None,
            updated_at=now,
        )
        self.visible = True

    async def set_provider_limit(self, *, provider, limit, updated_by_user_id):
        if provider is MeowProvider.KIE:
            self.runtime = MeowRuntimeSettings(
                **{
                    **self.runtime.__dict__,
                    "kie_concurrency_limit": limit,
                    "updated_by_user_id": updated_by_user_id,
                }
            )
        return self.runtime

    async def runtime_settings(self):
        return self.runtime

    async def can_use_meow(self, *, workspace_id, user_id, global_owner):
        return global_owner or (workspace_id == 7 and user_id == 77)

    async def workspace_settings(self, workspace_id):
        return self.workspace

    async def set_workspace_limit(self, *, workspace_id, limit, updated_by_user_id):
        self.workspace = WorkspaceMeowSettings(
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


class MeowRuntimeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_global_limits_are_owner_only_and_bounded(self) -> None:
        service = MeowRuntimeService(_FakeRepository())
        with self.assertRaises(MeowRuntimeAccessError):
            await service.set_provider_limit(
                actor_user_id=77,
                provider=MeowProvider.KIE,
                limit=50,
            )
        with self.assertRaises(ValueError):
            await service.set_provider_limit(
                actor_user_id=GLOBAL_WORKSPACE_CREATOR_ID,
                provider=MeowProvider.KIE,
                limit=101,
            )

    async def test_workspace_owner_can_select_limit_up_to_twenty(self) -> None:
        service = MeowRuntimeService(_FakeRepository())
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
        service = MeowRuntimeService(repository)
        visible = await service.set_module_visible(
            workspace_id=7,
            actor_user_id=77,
            is_visible=False,
        )
        self.assertFalse(visible)
        self.assertFalse(repository.visible)


class MeowModuleContractTests(unittest.TestCase):
    def test_meow_is_explicit_module_not_default_personal_grant(self) -> None:
        self.assertIn("meow", WORKSPACE_MODULE_KEYS)
        self.assertNotIn("meow", DEFAULT_PERSONAL_MODULE_KEYS)

    def test_cancel_callback_stays_within_telegram_limit(self) -> None:
        task_id = uuid4()
        keyboard = build_task_cancel_keyboard(workspace_id=7, task_id=task_id)
        callback_data = keyboard.inline_keyboard[0][0].callback_data
        self.assertIsNotNone(callback_data)
        self.assertLessEqual(len(callback_data or ""), 64)
        parsed = MeowRuntimeCallback.unpack(callback_data or "")
        self.assertEqual("cancel_task", parsed.action)
        self.assertEqual(str(task_id), parsed.value)

    def test_provider_routes_are_disjoint(self) -> None:
        self.assertTrue(
            set(MeowProvider.KIE.model_aliases).isdisjoint(
                MeowProvider.GRS.model_aliases
            )
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage import AITask, AITaskStatus
from velvet_bot.domains.media_generation import (
    KIE_GENERATION_TASK_TYPE,
    KieGenerationRequest,
    KieModelAlias,
    KieModelCatalog,
    KiePricing,
    KieTaskRecord,
    KieTaskState,
)
from velvet_bot.domains.media_generation.worker import KieGenerationWorker
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import WorkspaceModuleSetting
from velvet_bot.presentation.telegram.routers.workspace_meow import (
    build_meow_menu_keyboard,
    default_meow_request,
)
from velvet_bot.presentation.telegram.workspace_home_presentation import (
    build_workspace_owner_home_keyboard,
)


def _workspace() -> Workspace:
    now = datetime.now(UTC)
    return Workspace(9, "private-9", "Мой архив", False, now, now)


def _modules() -> tuple[WorkspaceModuleSetting, ...]:
    now = datetime.now(UTC)
    return (
        WorkspaceModuleSetting(
            workspace_id=9,
            module_key="archive",
            is_allowed=True,
            is_enabled=True,
            updated_by_user_id=1,
            created_at=now,
            updated_at=now,
        ),
    )


class MeowUIContractTests(unittest.TestCase):
    def test_owner_home_contains_exact_meow_label(self) -> None:
        keyboard = build_workspace_owner_home_keyboard(
            _workspace(),
            public_enabled=False,
            modules=_modules(),
        )
        labels = [
            button.text
            for row in keyboard.inline_keyboard
            for button in row
        ]
        self.assertIn("Мяу", labels)
        self.assertNotIn("🐈 Мяу", labels)

    def test_meow_menu_contains_three_generation_models(self) -> None:
        keyboard = build_meow_menu_keyboard(workspace_id=9, enabled=True)
        labels = [
            button.text
            for row in keyboard.inline_keyboard
            for button in row
        ]
        self.assertEqual(
            [
                "Seedream 5 Pro",
                "Nano Banana Pro",
                "Grok Imagine Video",
                "↩️ Моё пространство",
            ],
            labels,
        )

    def test_default_meow_profiles_are_vertical(self) -> None:
        nano = default_meow_request(
            KieModelAlias.NANO_BANANA_PRO,
            prompt="portrait",
        )
        grok = default_meow_request(
            KieModelAlias.GROK_IMAGINE_VIDEO,
            prompt="motion",
        )
        self.assertEqual("9:16", nano.aspect_ratio)
        self.assertEqual("2K", nano.resolution)
        self.assertEqual("9:16", grok.aspect_ratio)
        self.assertEqual("720p", grok.resolution)
        self.assertEqual(6, grok.duration_seconds)


class _FakeExecutor:
    def __init__(self) -> None:
        self.context = None

    async def execute(self, *, context, operation):
        self.context = context
        result = await operation()
        return result.value


class MeowWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_completes_queue_and_delivers_photo(self) -> None:
        now = datetime.now(UTC)
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            prompt="portrait",
            aspect_ratio="9:16",
            resolution="2K",
        )
        task = AITask(
            id=uuid4(),
            scope=AIBudgetScope.VISION,
            task_type=KIE_GENERATION_TASK_TYPE,
            status=AITaskStatus.RUNNING,
            priority=40,
            payload={
                "request": request.to_task_payload(),
                "chat_id": 100,
                "user_id": 200,
                "workspace_id": 9,
            },
            result={},
            dedupe_key=None,
            attempt_count=1,
            max_attempts=3,
            not_before=now,
            locked_by="kie-media-generation",
            locked_at=now,
            last_error_type=None,
            last_error=None,
            last_retry_delay_seconds=None,
            estimated_cost_rub=Decimal("9"),
            created_by=200,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
        queue = SimpleNamespace(
            claim_next=AsyncMock(return_value=task),
            heartbeat=AsyncMock(return_value=True),
            complete=AsyncMock(return_value=task),
            fail=AsyncMock(return_value=None),
        )
        client = SimpleNamespace(
            models=KieModelCatalog(seedream_5_pro="seedream/test"),
            create_task=AsyncMock(return_value="provider-1"),
            wait_for_task=AsyncMock(
                return_value=KieTaskRecord(
                    task_id="provider-1",
                    state=KieTaskState.SUCCESS,
                    result_urls=("https://cdn/result.png",),
                    consumed_credits=9,
                )
            ),
        )
        bot = SimpleNamespace(
            send_photo=AsyncMock(),
            send_video=AsyncMock(),
            send_message=AsyncMock(),
        )
        executor = _FakeExecutor()
        worker = KieGenerationWorker(
            bot=bot,
            queue=queue,
            client=client,
            executor=executor,
            pricing=KiePricing(),
            usd_to_rub=Decimal("100"),
        )

        processed = await worker.process_once()

        self.assertEqual(1, processed)
        queue.complete.assert_awaited_once()
        queue.fail.assert_not_awaited()
        bot.send_photo.assert_awaited_once()
        bot.send_video.assert_not_awaited()
        self.assertEqual("kie", executor.context.provider)
        self.assertEqual("media.generate", executor.context.operation)


if __name__ == "__main__":
    unittest.main()

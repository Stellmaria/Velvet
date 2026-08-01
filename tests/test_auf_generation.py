from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage import AITask, AITaskStatus
from velvet_bot.domains.auf_runtime import AUF_MODULE_KEY
from velvet_bot.domains.media_generation import (
    KIE_GENERATION_TASK_TYPE,
    KieContentMode,
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KieModelCatalog,
    KiePricing,
    KieReferenceImage,
    KieTaskRecord,
    KieTaskState,
    KieUploadedFile,
)
from velvet_bot.domains.media_generation.worker import (
    KieGenerationWorker,
    render_progress_bar,
)
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import WorkspaceModuleSetting
from velvet_bot.infrastructure.ai import KieError
from velvet_bot.presentation.telegram.routers.workspace_auf import (
    build_auf_mode_keyboard,
    build_auf_root_keyboard,
    build_model_keyboard,
    build_quality_keyboard,
    build_request_review_keyboard,
    format_request_review,
)
from velvet_bot.presentation.telegram.workspace_home_presentation import (
    build_workspace_owner_home_keyboard,
)


def _workspace() -> Workspace:
    now = datetime.now(UTC)
    return Workspace(9, "private-9", "Мой архив", False, now, now)


def _modules(
    *,
    auf_allowed: bool = True,
    auf_enabled: bool = True,
) -> tuple[WorkspaceModuleSetting, ...]:
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
        WorkspaceModuleSetting(
            workspace_id=9,
            module_key=AUF_MODULE_KEY,
            is_allowed=auf_allowed,
            is_enabled=auf_enabled if auf_allowed else False,
            updated_by_user_id=1,
            created_at=now,
            updated_at=now,
        ),
    )


def _labels(keyboard) -> list[str]:
    return [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]


def _reference() -> KieReferenceImage:
    return KieReferenceImage(
        telegram_file_id="tg-file",
        telegram_file_unique_id="tg-unique",
        source="library",
        mime_type="image/jpeg",
        file_name="kael.jpg",
        file_size=3,
        character_id=10,
        reference_id=20,
    )


def _task(request: KieGenerationRequest, *, attempt_count: int = 1) -> AITask:
    now = datetime.now(UTC)
    return AITask(
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
        attempt_count=attempt_count,
        max_attempts=3,
        not_before=now,
        locked_by="kie-media-generation",
        locked_at=now,
        last_error_type=None,
        last_error=None,
        last_retry_delay_seconds=None,
        estimated_cost_rub=Decimal("15"),
        created_by=200,
        created_at=now,
        updated_at=now,
        completed_at=None,
    )


class AufUIContractTests(unittest.TestCase):
    def test_owner_home_contains_auf_when_module_is_allowed_and_enabled(self) -> None:
        keyboard = build_workspace_owner_home_keyboard(
            _workspace(),
            public_enabled=False,
            modules=_modules(),
        )
        labels = _labels(keyboard)
        self.assertIn("Ауф", labels)
        self.assertNotIn("Мяу", labels)

    def test_owner_home_hides_auf_without_system_permission(self) -> None:
        keyboard = build_workspace_owner_home_keyboard(
            _workspace(),
            public_enabled=False,
            modules=_modules(auf_allowed=False, auf_enabled=False),
        )
        self.assertNotIn("Ауф", _labels(keyboard))

    def test_owner_home_hides_auf_when_workspace_disables_module(self) -> None:
        keyboard = build_workspace_owner_home_keyboard(
            _workspace(),
            public_enabled=False,
            modules=_modules(auf_allowed=True, auf_enabled=False),
        )
        self.assertNotIn("Ауф", _labels(keyboard))

    def test_generation_root_has_photo_and_video(self) -> None:
        self.assertEqual(
            ["Фото", "Видео", "↩️ Моё пространство"],
            _labels(build_auf_root_keyboard(workspace_id=9, enabled=True)),
        )

    def test_create_mode_has_text_photo_and_photo_text(self) -> None:
        labels = _labels(build_auf_mode_keyboard(workspace_id=9))
        self.assertEqual(
            ["Текст", "Фото", "Фото + текст", "Отмена"],
            labels,
        )

    def test_review_has_exact_three_actions(self) -> None:
        labels = _labels(build_request_review_keyboard(workspace_id=9))
        self.assertEqual(
            ["Да, подтвердить", "Изменить", "Отмена"],
            labels,
        )

    def test_only_two_photo_models_are_exposed(self) -> None:
        labels = _labels(build_model_keyboard(workspace_id=9))
        self.assertEqual(
            [
                "Nano Banana Pro",
                "Seedream 5 Pro",
                "↩️ К проверке",
                "Отмена",
            ],
            labels,
        )
        self.assertNotIn("Grok Imagine Video", labels)

    def test_quality_buttons_follow_model_capabilities(self) -> None:
        nano = _labels(
            build_quality_keyboard(
                workspace_id=9,
                model=KieModelAlias.NANO_BANANA_PRO,
            )
        )
        seedream = _labels(
            build_quality_keyboard(
                workspace_id=9,
                model=KieModelAlias.SEEDREAM_5_PRO,
            )
        )
        self.assertEqual(["1K", "2K", "4K", "↩️ К моделям", "Отмена"], nano)
        self.assertEqual(["1K", "2K", "↩️ К моделям", "Отмена"], seedream)

    def test_review_discloses_mature_and_reference_sources(self) -> None:
        text = format_request_review(
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt="portrait in a dark studio",
            references=(
                _reference(),
                KieReferenceImage(
                    telegram_file_id="upload-file",
                    telegram_file_unique_id="upload-unique",
                    source="upload",
                    mime_type="image/png",
                    file_name="upload.png",
                ),
            ),
        )
        self.assertIn("Режим: <b>Фото + текст</b>", text)
        self.assertIn("из базы 1, отправлено 1", text)
        self.assertIn("Контент: <b>Mature</b>", text)

    def test_progress_bar_is_bounded_and_visible(self) -> None:
        self.assertEqual("░░░░░░░░░░", render_progress_bar(-5))
        self.assertEqual("█████░░░░░", render_progress_bar(50))
        self.assertEqual("██████████", render_progress_bar(120))


class _FakeExecutor:
    def __init__(self) -> None:
        self.context = None

    async def execute(self, *, context, operation):
        self.context = context
        result = await operation()
        return result.value


class _FakeBot:
    def __init__(self) -> None:
        self.send_photo = AsyncMock()
        self.send_video = AsyncMock()
        self.send_message = AsyncMock(
            return_value=SimpleNamespace(message_id=777)
        )
        self.edit_message_text = AsyncMock()
        self.downloaded_file_ids: list[str] = []

    async def download(self, file_id, *, destination, timeout, seek):
        self.downloaded_file_ids.append(str(file_id))
        destination.write(b"abc")
        if seek:
            destination.seek(0)
        return destination


class AufWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_uploads_reference_then_generates_seedream_photo(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.SEEDREAM_5_PRO,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt="portrait",
            references=(_reference(),),
            content_mode=KieContentMode.MATURE,
            aspect_ratio="9:16",
            resolution="2K",
        )
        task = _task(request)
        queue = SimpleNamespace(
            claim_next=AsyncMock(return_value=task),
            heartbeat=AsyncMock(return_value=True),
            complete=AsyncMock(return_value=task),
            fail=AsyncMock(return_value=None),
        )
        client = SimpleNamespace(
            models=KieModelCatalog(
                seedream_5_pro_image="seedream/5-pro-image-to-image"
            ),
            upload_reference=AsyncMock(
                return_value=KieUploadedFile(
                    file_url="https://temp.example/reference.jpg"
                )
            ),
            create_task=AsyncMock(return_value="provider-1"),
            wait_for_task=AsyncMock(
                return_value=KieTaskRecord(
                    task_id="provider-1",
                    state=KieTaskState.SUCCESS,
                    result_urls=("https://cdn/result.png",),
                    consumed_credits=15,
                )
            ),
        )
        bot = _FakeBot()
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
        self.assertEqual(["tg-file"], bot.downloaded_file_ids)
        client.upload_reference.assert_awaited_once()
        provider_request = client.create_task.await_args.args[0]
        self.assertEqual(
            ("https://temp.example/reference.jpg",),
            provider_request.image_urls,
        )
        provider_payload = provider_request.to_input()
        self.assertEqual(
            ["https://temp.example/reference.jpg"],
            provider_payload["image_urls"],
        )
        self.assertIs(False, provider_payload["nsfw_checker"])
        queue.complete.assert_awaited_once()
        queue.fail.assert_not_awaited()
        bot.send_photo.assert_awaited_once()
        bot.send_video.assert_not_awaited()
        bot.edit_message_text.assert_awaited()
        progress_texts = [
            call.args[0]
            for call in bot.edit_message_text.await_args_list
        ]
        self.assertTrue(any("100%" in text for text in progress_texts))
        self.assertEqual("kie", executor.context.provider)
        self.assertEqual("media.generate", executor.context.operation)
        self.assertEqual(1, executor.context.metadata["reference_count"])

    async def test_failed_generation_is_requeued_and_progress_discloses_retry(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            input_mode=KieInputMode.TEXT,
            prompt="portrait",
            resolution="1K",
        )
        task = _task(request)
        failure = SimpleNamespace(
            will_retry=True,
            retry_delay_seconds=5,
        )
        queue = SimpleNamespace(
            claim_next=AsyncMock(return_value=task),
            heartbeat=AsyncMock(return_value=True),
            complete=AsyncMock(),
            fail=AsyncMock(return_value=failure),
        )
        client = SimpleNamespace(
            models=KieModelCatalog(),
            create_task=AsyncMock(side_effect=KieError("provider unavailable")),
            wait_for_task=AsyncMock(),
            upload_reference=AsyncMock(),
        )
        bot = _FakeBot()
        worker = KieGenerationWorker(
            bot=bot,
            queue=queue,
            client=client,
            executor=_FakeExecutor(),
            pricing=KiePricing(),
            usd_to_rub=Decimal("100"),
        )

        processed = await worker.process_once()

        self.assertEqual(1, processed)
        queue.complete.assert_not_awaited()
        queue.fail.assert_awaited_once()
        self.assertEqual(
            5,
            queue.fail.await_args.kwargs["base_delay_seconds"],
        )
        self.assertEqual(
            30,
            queue.fail.await_args.kwargs["max_delay_seconds"],
        )
        progress_texts = [
            call.args[0]
            for call in bot.edit_message_text.await_args_list
        ]
        self.assertTrue(
            any("Автоповтор 2/3 через 5 сек." in text for text in progress_texts)
        )


if __name__ == "__main__":
    unittest.main()

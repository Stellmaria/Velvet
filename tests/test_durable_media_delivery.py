from __future__ import annotations

import unittest
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from velvet_bot.application.media_delivery import (
    DeliverMediaResult,
    DownloadedMedia,
    MediaDeliveryItem,
    MediaDeliveryJob,
    MediaDeliveryStatus,
    MediaDeliveryStepStatus,
    MediaUrlExpired,
    RedeliverMediaResult,
    ResolveProviderResult,
)
from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage import AITask, AITaskStatus
from velvet_bot.domains.media_generation.friendly_worker import FriendlyKieGenerationWorker
from velvet_bot.domains.media_generation.task_queue import KieTaskQueueService


class _Repository:
    def __init__(self, job: MediaDeliveryJob) -> None:
        self.job = job
        self.claimed = False
        self.events: list[tuple[str, object]] = []
        self.backfilled = False
        self.reset = False

    async def claim(self, **kwargs):
        if self.claimed:
            return None
        self.claimed = True
        return self.job

    async def claim_resolution(self, **kwargs):
        if self.claimed:
            return None
        self.claimed = True
        return self.job

    async def finish_resolution(self, **kwargs) -> None:
        self.events.append(("finish-resolution", kwargs))

    async def record_provider_success(self, **kwargs) -> None:
        self.events.append(("provider-success", kwargs))

    async def mark_download(self, **kwargs) -> None:
        self.events.append(("download", kwargs))

    async def mark_channel(self, **kwargs) -> None:
        self.events.append(("channel", kwargs))

    async def mark_notification(self, **kwargs) -> None:
        self.events.append(("notification", kwargs))

    async def finish(self, **kwargs) -> None:
        self.events.append(("finish", kwargs))

    async def backfill_task(self, **kwargs) -> bool:
        self.backfilled = True
        return True

    async def reset_for_redelivery(self, **kwargs) -> bool:
        self.reset = True
        self.claimed = False
        return True


class _Transport:
    def __init__(
        self,
        *,
        original_error: BaseException | None = None,
        preview_error: BaseException | None = None,
        download_error: BaseException | None = None,
    ) -> None:
        self.original_error = original_error
        self.preview_error = preview_error
        self.download_error = download_error
        self.calls: list[str] = []

    async def download(self, **kwargs) -> DownloadedMedia:
        self.calls.append("download")
        if self.download_error is not None:
            raise self.download_error
        return DownloadedMedia(
            payload=b"payload",
            file_name="result.png",
            content_type="image/png",
        )

    async def send_original(self, **kwargs) -> None:
        self.calls.append("original")
        if self.original_error is not None:
            raise self.original_error

    async def send_preview(self, **kwargs) -> None:
        self.calls.append("preview")
        if self.preview_error is not None:
            raise self.preview_error

    async def send_direct_preview(self, **kwargs) -> None:
        self.calls.append("direct-preview")

    async def notify(self, **kwargs) -> None:
        self.calls.append("notify")


class _ProviderResolver:
    def __init__(self, urls: tuple[str, ...]) -> None:
        self.urls = urls
        self.calls: list[tuple[str, str]] = []

    async def resolve(self, *, provider: str, provider_task_id: str) -> tuple[str, ...]:
        self.calls.append((provider, provider_task_id))
        return self.urls


def _job(
    *,
    attempt_count: int = 1,
    status: MediaDeliveryStatus = MediaDeliveryStatus.RESULT_RESOLVED,
    items: bool = True,
) -> MediaDeliveryJob:
    return MediaDeliveryJob(
        task_id=uuid4(),
        provider="grs",
        provider_task_id="grs:task",
        chat_id=100,
        media_kind="image",
        request={"model": "nano_banana_pro"},
        status=status,
        attempt_count=attempt_count,
        notification_status=MediaDeliveryStepStatus.PENDING,
        items=(
            MediaDeliveryItem(
                result_index=1,
                result_url="https://cdn.example/result.png",
                url_status="available",
                download_status=MediaDeliveryStepStatus.PENDING,
                original_status=MediaDeliveryStepStatus.PENDING,
                preview_status=MediaDeliveryStepStatus.PENDING,
            ),
        ) if items else (),
    )


class DurableMediaDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_original_failure_does_not_block_preview_or_rerun_provider(self) -> None:
        job = _job()
        repository = _Repository(job)
        transport = _Transport(original_error=RuntimeError("document rejected"))

        summary = await DeliverMediaResult(
            repository=repository,
            transport=transport,
            max_attempts=3,
        ).execute(task_id=job.task_id)

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(MediaDeliveryStatus.RETRY, summary.status)
        self.assertEqual(0, summary.original_sent)
        self.assertEqual(1, summary.preview_sent)
        self.assertEqual(["download", "original", "preview"], transport.calls)

    async def test_preview_failure_does_not_erase_successful_original(self) -> None:
        job = _job(attempt_count=12)
        repository = _Repository(job)
        transport = _Transport(preview_error=RuntimeError("preview rejected"))

        summary = await DeliverMediaResult(
            repository=repository,
            transport=transport,
            max_attempts=12,
        ).execute(task_id=job.task_id)

        assert summary is not None
        self.assertEqual(MediaDeliveryStatus.PARTIAL, summary.status)
        self.assertEqual(1, summary.original_sent)
        self.assertEqual(0, summary.preview_sent)
        self.assertEqual(["download", "original", "preview", "notify"], transport.calls)

    async def test_expired_url_is_terminal_and_explicit(self) -> None:
        job = _job()
        repository = _Repository(job)
        transport = _Transport(download_error=MediaUrlExpired("HTTP 410"))

        summary = await DeliverMediaResult(
            repository=repository,
            transport=transport,
        ).execute(task_id=job.task_id)

        assert summary is not None
        self.assertEqual(MediaDeliveryStatus.EXPIRED, summary.status)
        self.assertFalse(summary.retry_scheduled)
        self.assertEqual(["download", "notify"], transport.calls)

    async def test_provider_success_without_url_is_resolved_without_submit(self) -> None:
        job = _job(status=MediaDeliveryStatus.PROVIDER_SUCCESS, items=False)
        repository = _Repository(job)
        provider = _ProviderResolver(("https://cdn.example/later.png",))

        resolved = await ResolveProviderResult(
            repository,
            provider,
        ).execute(task_id=job.task_id)

        self.assertTrue(resolved)
        self.assertEqual([("grs", "grs:task")], provider.calls)
        saved = [payload for name, payload in repository.events if name == "provider-success"]
        self.assertEqual(("https://cdn.example/later.png",), saved[0]["result_urls"])

    async def test_redelivery_resets_state_without_generation_api(self) -> None:
        job = _job()
        repository = _Repository(job)
        transport = _Transport()
        delivery = DeliverMediaResult(repository=repository, transport=transport)

        summary = await RedeliverMediaResult(
            repository=repository,
            delivery=delivery,
        ).execute(task_id=job.task_id, chat_id=200)

        self.assertTrue(repository.backfilled)
        self.assertTrue(repository.reset)
        self.assertIsNotNone(summary)
        self.assertEqual(["download", "original", "preview", "notify"], transport.calls)


class _FakeConnection:
    async def execute(self, query: str, *arguments: object) -> str:
        return "UPDATE 1"


class _FakeDatabase:
    @asynccontextmanager
    async def acquire(self):
        yield _FakeConnection()


class DurableMediaQueueContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_restart_after_provider_success_resumes_same_paid_task(self) -> None:
        now = datetime.now(timezone.utc)
        task = AITask(
            id=uuid4(),
            scope=AIBudgetScope.VISION,
            task_type="media.generate.kie",
            status=AITaskStatus.RUNNING,
            priority=100,
            payload={
                "kie_campaign": {
                    "status": "success",
                    "last_provider_task_id": "grs:already-paid",
                    "active_provider_task_id": None,
                }
            },
            result={},
            dedupe_key=None,
            attempt_count=2,
            max_attempts=50,
            not_before=now,
            locked_by="worker",
            locked_at=now,
            last_error_type=None,
            last_error=None,
            last_retry_delay_seconds=None,
            estimated_cost_rub=Decimal("0"),
            created_by=None,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
        queue = object.__new__(KieTaskQueueService)
        queue._database = _FakeDatabase()

        restored = await queue._restore_successful_provider_task(
            task=task,
            worker_id="worker",
        )

        runtime = restored.payload["kie_campaign"]
        self.assertEqual("grs:already-paid", runtime["active_provider_task_id"])
        self.assertEqual("running", runtime["status"])

    async def test_active_worker_disables_inherited_best_effort_delivery(self) -> None:
        worker = object.__new__(FriendlyKieGenerationWorker)
        handler = FriendlyKieGenerationWorker.__dict__["_deliver_best_effort"]

        self.assertEqual("_deliver_best_effort", handler.__name__)
        await handler(worker, chat_id=None, request=None, record=None)  # type: ignore[arg-type]

    def test_legacy_delivery_installers_are_retired(self) -> None:
        retired = (
            "velvet_bot/app/original_image_delivery_hotfix.py",
            "velvet_bot/app/original_video_delivery_hotfix.py",
            "velvet_bot/app/auf_result_delivery_recovery.py",
            "velvet_bot/app/auf_active_delivery_fix.py",
        )
        for path in retired:
            self.assertFalse(Path(path).exists(), path)

        composition = Path("velvet_bot/app/composition.py").read_text(encoding="utf-8")
        friendly = Path("velvet_bot/domains/media_generation/friendly_worker.py").read_text(
            encoding="utf-8"
        )
        base_worker = Path(
            "velvet_bot/domains/media_generation/file_delivery_worker.py"
        ).read_text(encoding="utf-8")
        for token in (
            "install_original_image_delivery_hotfix",
            "install_original_video_delivery_hotfix",
            "install_auf_result_delivery_recovery",
            "install_auf_active_delivery_fix",
        ):
            self.assertNotIn(token, composition)
            self.assertNotIn(token, friendly)
        self.assertIn("install_media_delivery_ui()", friendly)
        self.assertNotIn("_disable_legacy_delivery_installers", friendly)
        self.assertNotIn("install_delivery_handler", base_worker)

    def test_migration_models_independent_delivery_channels_and_resolution(self) -> None:
        migration = Path("migrations/z029_durable_media_delivery.sql").read_text(
            encoding="utf-8"
        )
        for token in (
            "media_delivery_jobs",
            "media_delivery_items",
            "provider_task_id",
            "result_resolution_attempts",
            "result_url",
            "original_status",
            "preview_status",
            "notification_status",
            "expired",
        ):
            self.assertIn(token, migration)


if __name__ == "__main__":
    unittest.main()

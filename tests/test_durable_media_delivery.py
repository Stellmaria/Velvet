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
    MediaDeliveryRepositoryError,
    MediaDeliveryStatus,
    MediaDeliveryStepStatus,
    MediaDeliveryTransportError,
    MediaUrlExpired,
    ProviderResultPending,
    ProviderResultTerminal,
    RedeliverMediaResult,
    ResolveProviderResult,
)
from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage import AITask, AITaskStatus
from velvet_bot.domains.media_generation.friendly_worker import FriendlyKieGenerationWorker
from velvet_bot.domains.media_generation.task_queue import KieTaskQueueService


def _transport_error(
    message: str,
    *,
    retryable: bool = True,
) -> MediaDeliveryTransportError:
    return MediaDeliveryTransportError(
        message,
        code="transport_test_failure",
        retryable=retryable,
    )


class _Repository:
    def __init__(
        self,
        job: MediaDeliveryJob,
        *,
        fail_channel_success: str | None = None,
    ) -> None:
        self.job = job
        self.claimed = False
        self.events: list[tuple[str, object]] = []
        self.backfilled = False
        self.reset = False
        self.fail_channel_success = fail_channel_success
        self._channel_success_failed = False

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
        if (
            not self._channel_success_failed
            and kwargs.get("channel") == self.fail_channel_success
            and kwargs.get("status") is MediaDeliveryStepStatus.SUCCESS
        ):
            self._channel_success_failed = True
            raise MediaDeliveryRepositoryError(
                "test_mark_channel_success",
                RuntimeError("database unavailable after Telegram accepted media"),
            )

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
        notify_error: BaseException | None = None,
        preserve_raw_errors: bool = False,
    ) -> None:
        self.original_error = original_error
        self.preview_error = preview_error
        self.download_error = download_error
        self.notify_error = notify_error
        self.preserve_raw_errors = preserve_raw_errors
        self.calls: list[str] = []

    def _raise(self, error: BaseException | None) -> None:
        if error is None:
            return
        if self.preserve_raw_errors or isinstance(
            error,
            (MediaDeliveryTransportError, MediaUrlExpired),
        ):
            raise error
        raise _transport_error(str(error)) from error

    async def download(self, **kwargs) -> DownloadedMedia:
        self.calls.append("download")
        self._raise(self.download_error)
        return DownloadedMedia(
            payload=b"payload",
            file_name="result.png",
            content_type="image/png",
        )

    async def send_original(self, **kwargs) -> None:
        self.calls.append("original")
        self._raise(self.original_error)

    async def send_preview(self, **kwargs) -> None:
        self.calls.append("preview")
        self._raise(self.preview_error)

    async def send_direct_preview(self, **kwargs) -> None:
        self.calls.append("direct-preview")
        self._raise(self.preview_error)

    async def notify(self, **kwargs) -> None:
        self.calls.append("notify")
        self._raise(self.notify_error)


class _ProviderResolver:
    def __init__(
        self,
        urls: tuple[str, ...] = (),
        *,
        error: BaseException | None = None,
    ) -> None:
        self.urls = urls
        self.error = error
        self.calls: list[tuple[str, str]] = []

    async def resolve(
        self,
        *,
        provider: str,
        provider_task_id: str,
    ) -> tuple[str, ...]:
        self.calls.append((provider, provider_task_id))
        if self.error is not None:
            raise self.error
        return self.urls


def _job(
    *,
    attempt_count: int = 1,
    status: MediaDeliveryStatus = MediaDeliveryStatus.RESULT_RESOLVED,
    items: bool = True,
    original_status: MediaDeliveryStepStatus = MediaDeliveryStepStatus.PENDING,
    preview_status: MediaDeliveryStepStatus = MediaDeliveryStepStatus.PENDING,
    notification_status: MediaDeliveryStepStatus = MediaDeliveryStepStatus.PENDING,
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
        notification_status=notification_status,
        items=(
            MediaDeliveryItem(
                result_index=1,
                result_url="https://cdn.example/result.png",
                url_status="available",
                download_status=MediaDeliveryStepStatus.PENDING,
                original_status=original_status,
                preview_status=preview_status,
            ),
        )
        if items
        else (),
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
        original_states = [
            payload["status"]
            for name, payload in repository.events
            if name == "channel" and payload["channel"] == "original"
        ]
        self.assertEqual(
            [MediaDeliveryStepStatus.SENDING, MediaDeliveryStepStatus.FAILED],
            original_states,
        )

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

    async def test_post_send_repository_failure_becomes_uncertain_without_retry(self) -> None:
        job = _job()
        repository = _Repository(job, fail_channel_success="original")
        transport = _Transport()

        summary = await DeliverMediaResult(
            repository=repository,
            transport=transport,
        ).execute(task_id=job.task_id)

        assert summary is not None
        self.assertEqual(MediaDeliveryStatus.PARTIAL, summary.status)
        self.assertEqual(0, summary.original_sent)
        self.assertEqual(1, summary.preview_sent)
        self.assertEqual(1, summary.uncertain_channels)
        self.assertFalse(summary.retry_scheduled)
        states = [
            payload["status"]
            for name, payload in repository.events
            if name == "channel" and payload["channel"] == "original"
        ]
        self.assertEqual(
            [
                MediaDeliveryStepStatus.SENDING,
                MediaDeliveryStepStatus.SUCCESS,
                MediaDeliveryStepStatus.UNCERTAIN,
            ],
            states,
        )

    async def test_reclaimed_sending_channel_is_not_sent_again(self) -> None:
        job = _job(
            original_status=MediaDeliveryStepStatus.SENDING,
            preview_status=MediaDeliveryStepStatus.SUCCESS,
            notification_status=MediaDeliveryStepStatus.SUCCESS,
        )
        repository = _Repository(job)
        transport = _Transport()

        summary = await DeliverMediaResult(
            repository=repository,
            transport=transport,
        ).execute(task_id=job.task_id)

        assert summary is not None
        self.assertEqual(MediaDeliveryStatus.PARTIAL, summary.status)
        self.assertEqual(1, summary.uncertain_channels)
        self.assertEqual([], transport.calls)
        self.assertFalse(summary.retry_scheduled)

    async def test_unexpected_programming_error_is_not_masked_as_delivery_failure(self) -> None:
        job = _job()
        repository = _Repository(job)
        transport = _Transport(
            original_error=TypeError("broken adapter contract"),
            preserve_raw_errors=True,
        )

        with self.assertRaisesRegex(TypeError, "broken adapter contract"):
            await DeliverMediaResult(
                repository=repository,
                transport=transport,
            ).execute(task_id=job.task_id)

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
        saved = [
            payload
            for name, payload in repository.events
            if name == "provider-success"
        ]
        self.assertEqual(("https://cdn.example/later.png",), saved[0]["result_urls"])

    async def test_provider_pending_schedules_resolution_retry(self) -> None:
        job = _job(status=MediaDeliveryStatus.PROVIDER_SUCCESS, items=False)
        repository = _Repository(job)
        provider = _ProviderResolver(error=ProviderResultPending("still processing"))

        resolved = await ResolveProviderResult(repository, provider).execute(
            task_id=job.task_id
        )

        self.assertFalse(resolved)
        payload = [
            value
            for name, value in repository.events
            if name == "finish-resolution"
        ][0]
        self.assertFalse(payload["terminal"])
        self.assertIsNotNone(payload["retry_delay_seconds"])

    async def test_provider_terminal_failure_does_not_retry_resolution(self) -> None:
        job = _job(status=MediaDeliveryStatus.PROVIDER_SUCCESS, items=False)
        repository = _Repository(job)
        provider = _ProviderResolver(error=ProviderResultTerminal("provider failed"))

        resolved = await ResolveProviderResult(repository, provider).execute(
            task_id=job.task_id
        )

        self.assertFalse(resolved)
        payload = [
            value
            for name, value in repository.events
            if name == "finish-resolution"
        ][0]
        self.assertTrue(payload["terminal"])
        self.assertIsNone(payload["retry_delay_seconds"])

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

    async def test_legacy_worker_override_cannot_steal_delivery_ownership(self) -> None:
        class LegacyOverride(FriendlyKieGenerationWorker):
            async def _deliver_best_effort(self, **kwargs) -> None:
                raise AssertionError("legacy delivery override executed")

        worker = object.__new__(LegacyOverride)
        guarded = worker._deliver_best_effort

        self.assertEqual("_durable_delivery_guard", guarded.__name__)
        await guarded(chat_id=None, request=None, record=None)  # type: ignore[arg-type]

    def test_compatibility_installer_stages_are_explicitly_neutralized(self) -> None:
        source = Path(
            "velvet_bot/domains/media_generation/friendly_worker.py"
        ).read_text(encoding="utf-8")
        for module_name in (
            "original_image_delivery_hotfix",
            "original_video_delivery_hotfix",
            "auf_result_delivery_recovery",
            "auf_active_delivery_fix",
        ):
            self.assertIn(module_name, source)
        self.assertIn("module._INSTALLED = True", source)

    def test_migrations_model_ambiguous_delivery_without_auto_retry(self) -> None:
        base = Path("migrations/z029_durable_media_delivery.sql").read_text(
            encoding="utf-8"
        )
        uncertain = Path(
            "migrations/z030_media_delivery_uncertain_states.sql"
        ).read_text(encoding="utf-8")
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
            self.assertIn(token, base)
        self.assertIn("'sending'", uncertain)
        self.assertIn("'uncertain'", uncertain)

    def test_target_media_delivery_files_have_no_unresolved_broad_catches(self) -> None:
        for relative in (
            "velvet_bot/application/media_delivery_deliver.py",
            "velvet_bot/application/media_delivery_resolve.py",
            "velvet_bot/domains/media_generation/task_queue.py",
            "velvet_bot/domains/media_generation/friendly_worker.py",
            "velvet_bot/infrastructure/media_delivery_runtime.py",
        ):
            source = Path(relative).read_text(encoding="utf-8")
            self.assertNotIn("except Exception", source, relative)


if __name__ == "__main__":
    unittest.main()

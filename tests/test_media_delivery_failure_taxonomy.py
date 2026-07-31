from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from velvet_bot.application.media_delivery import (
    DeliverMediaResult,
    DownloadedMedia,
    MediaDeliveryItem,
    MediaDeliveryJob,
    MediaDeliveryStatus,
    MediaDeliveryStepStatus,
    classify_media_delivery_error,
    media_delivery_error_text,
)


class _StateRepository:
    def __init__(self, job: MediaDeliveryJob) -> None:
        self.job = job
        self.events: list[tuple[str, object]] = []
        self.fail_original_success_once = False
        self.fail_finish_once = False
        self.finished_statuses: list[MediaDeliveryStatus] = []

    async def claim(self, **kwargs) -> MediaDeliveryJob | None:
        del kwargs
        if self.job.status in {
            MediaDeliveryStatus.DELIVERED,
            MediaDeliveryStatus.PARTIAL,
            MediaDeliveryStatus.EXPIRED,
            MediaDeliveryStatus.FAILED,
        }:
            return None
        self.job = replace(
            self.job,
            status=MediaDeliveryStatus.DELIVERING,
            attempt_count=self.job.attempt_count + 1,
        )
        return self.job

    async def mark_download(self, **kwargs) -> None:
        self.events.append(("download", kwargs))
        index = int(kwargs["result_index"])
        status = kwargs["status"]
        self._replace_item(
            index,
            download_status=status,
            content_type=kwargs.get("content_type"),
            file_name=kwargs.get("file_name"),
        )

    async def mark_channel(self, **kwargs) -> None:
        self.events.append(("channel", kwargs))
        index = int(kwargs["result_index"])
        channel = str(kwargs["channel"])
        status = kwargs["status"]
        if (
            self.fail_original_success_once
            and channel == "original"
            and status is MediaDeliveryStepStatus.SUCCESS
        ):
            self.fail_original_success_once = False
            raise OSError("database unavailable after Telegram send")
        self._replace_item(index, **{f"{channel}_status": status})

    async def mark_notification(self, **kwargs) -> None:
        self.events.append(("notification", kwargs))
        self.job = replace(self.job, notification_status=kwargs["status"])

    async def finish(self, **kwargs) -> None:
        self.events.append(("finish", kwargs))
        if self.fail_finish_once:
            self.fail_finish_once = False
            raise OSError("database unavailable during finish")
        status = kwargs["status"]
        self.finished_statuses.append(status)
        self.job = replace(self.job, status=status)

    def _replace_item(self, result_index: int, **changes: object) -> None:
        items = []
        for item in self.job.items:
            if item.result_index == result_index:
                filtered = {
                    key: value
                    for key, value in changes.items()
                    if value is not None
                }
                item = replace(item, **filtered)
            items.append(item)
        self.job = replace(self.job, items=tuple(items))


class _Transport:
    def __init__(self, *, original_error: BaseException | None = None) -> None:
        self.original_error = original_error
        self.calls: list[str] = []

    async def download(self, **kwargs) -> DownloadedMedia:
        del kwargs
        self.calls.append("download")
        return DownloadedMedia(
            payload=b"result",
            file_name="result.png",
            content_type="image/png",
        )

    async def send_original(self, **kwargs) -> None:
        del kwargs
        self.calls.append("original")
        if self.original_error is not None:
            raise self.original_error

    async def send_preview(self, **kwargs) -> None:
        del kwargs
        self.calls.append("preview")

    async def send_direct_preview(self, **kwargs) -> None:
        del kwargs
        self.calls.append("direct-preview")

    async def notify(self, **kwargs) -> None:
        del kwargs
        self.calls.append("notify")


def _job() -> MediaDeliveryJob:
    return MediaDeliveryJob(
        task_id=uuid4(),
        provider="kie",
        provider_task_id="provider-task",
        chat_id=100,
        media_kind="image",
        request={"model": "qwen2_image_edit"},
        status=MediaDeliveryStatus.RESULT_RESOLVED,
        attempt_count=0,
        notification_status=MediaDeliveryStepStatus.PENDING,
        items=(
            MediaDeliveryItem(
                result_index=1,
                result_url="https://provider.invalid/result.png",
                url_status="available",
                download_status=MediaDeliveryStepStatus.PENDING,
                original_status=MediaDeliveryStepStatus.PENDING,
                preview_status=MediaDeliveryStepStatus.PENDING,
            ),
        ),
    )


class MediaDeliveryFailureTaxonomyTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_success_then_state_failure_does_not_duplicate_original(self) -> None:
        repository = _StateRepository(_job())
        repository.fail_original_success_once = True
        transport = _Transport()
        delivery = DeliverMediaResult(
            repository=repository,
            transport=transport,
            max_attempts=4,
        )

        first = await delivery.execute()
        second = await delivery.execute()

        assert first is not None
        assert second is not None
        self.assertEqual(MediaDeliveryStatus.RETRY, first.status)
        self.assertEqual(MediaDeliveryStatus.PARTIAL, second.status)
        self.assertEqual(1, transport.calls.count("original"))
        self.assertEqual(1, transport.calls.count("preview"))
        self.assertEqual(
            MediaDeliveryStepStatus.UNCERTAIN,
            repository.job.items[0].original_status,
        )

    async def test_finish_failure_recovery_does_not_resend_successful_channels(self) -> None:
        repository = _StateRepository(_job())
        repository.fail_finish_once = True
        transport = _Transport()
        delivery = DeliverMediaResult(
            repository=repository,
            transport=transport,
            max_attempts=4,
        )

        first = await delivery.execute()
        second = await delivery.execute()

        assert first is not None
        assert second is not None
        self.assertEqual(MediaDeliveryStatus.RETRY, first.status)
        self.assertEqual(MediaDeliveryStatus.DELIVERED, second.status)
        self.assertEqual(1, transport.calls.count("original"))
        self.assertEqual(1, transport.calls.count("preview"))
        self.assertEqual(1, transport.calls.count("notify"))

    async def test_programming_error_is_compensated_and_re_raised(self) -> None:
        repository = _StateRepository(_job())
        delivery = DeliverMediaResult(
            repository=repository,
            transport=_Transport(original_error=TypeError("bad adapter contract")),
        )

        with self.assertRaisesRegex(TypeError, "bad adapter contract"):
            await delivery.execute()

        self.assertEqual([MediaDeliveryStatus.FAILED], repository.finished_statuses)

    def test_durable_error_payload_is_structured_and_redacted(self) -> None:
        raw = (
            "https://provider.invalid/result.png?token=secret "
            "chat_id=123 prompt=user-content"
        )
        error = RuntimeError(raw)
        encoded = media_delivery_error_text(error, phase="download")
        assert encoded is not None
        payload = json.loads(encoded)

        self.assertEqual("operational_runtime_error", payload["code"])
        self.assertEqual("transient", payload["kind"])
        self.assertEqual(20, len(payload["fingerprint"]))
        self.assertNotIn("secret", encoded)
        self.assertNotIn("provider.invalid", encoded)
        self.assertNotIn("user-content", encoded)
        self.assertEqual(
            payload,
            json.loads(
                classify_media_delivery_error(error, phase="download").as_json()
            ),
        )

    def test_schema_supports_uncertain_and_structured_error_fields(self) -> None:
        migration = Path(
            "migrations/z030_media_delivery_failure_taxonomy.sql"
        ).read_text(encoding="utf-8")
        finish = Path(
            "velvet_bot/infrastructure/media_delivery_repository_finish.py"
        ).read_text(encoding="utf-8")

        for token in (
            "uncertain",
            "last_error_code",
            "last_error_fingerprint",
            "original_error_code",
            "preview_error_fingerprint",
        ):
            self.assertIn(token, migration)
        self.assertIn("WHEN {status_column}='success' THEN 'success'", finish)
        self.assertIn("{attempts_column}={attempts_column}+CASE", finish)
        self.assertIn("finish_delivery_claim", finish)


if __name__ == "__main__":
    unittest.main()

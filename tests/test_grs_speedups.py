from __future__ import annotations

import asyncio
import unittest
from decimal import Decimal
from types import SimpleNamespace

import velvet_bot.app.grs_speedups as speedups
from velvet_bot.app.grs_speedups import _fast_upload_references
from velvet_bot.domains.media_generation import (
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KieReferenceImage,
)
from velvet_bot.presentation.telegram.routers.workspace_auf_grs_balance import (
    _render_grs_balance,
)


class _FakeQueue:
    def __init__(self) -> None:
        self.heartbeats = 0

    async def heartbeat(self, **_: object) -> None:
        self.heartbeats += 1


class _FakeClient:
    def __init__(self, worker: "_FakeWorker") -> None:
        self._worker = worker

    async def upload_reference(
        self,
        payload: bytes,
        *,
        mime_type: str,
        file_name: str,
    ) -> SimpleNamespace:
        del payload, mime_type
        self._worker.active_uploads += 1
        self._worker.max_active_uploads = max(
            self._worker.max_active_uploads,
            self._worker.active_uploads,
        )
        self._worker.upload_calls += 1
        try:
            await asyncio.sleep(0.01)
            return SimpleNamespace(file_url=f"https://files.invalid/{file_name}")
        finally:
            self._worker.active_uploads -= 1


class _FakeWorker:
    def __init__(self) -> None:
        self._queue = _FakeQueue()
        self._worker_id = "test-worker"
        self._client = _FakeClient(self)
        self.download_calls = 0
        self.upload_calls = 0
        self.active_downloads = 0
        self.max_active_downloads = 0
        self.active_uploads = 0
        self.max_active_uploads = 0

    async def _download_reference(self, reference: KieReferenceImage) -> bytes:
        self.active_downloads += 1
        self.max_active_downloads = max(
            self.max_active_downloads,
            self.active_downloads,
        )
        self.download_calls += 1
        try:
            await asyncio.sleep(0.01)
            return reference.telegram_file_id.encode("utf-8")
        finally:
            self.active_downloads -= 1

    async def _publish_progress(self, *args: object, **kwargs: object) -> None:
        del args, kwargs


class GrsReferenceSpeedupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        async with speedups._REFERENCE_CACHE_LOCK:
            speedups._REFERENCE_URL_CACHE.clear()

    async def test_references_upload_concurrently_and_keep_input_order(self) -> None:
        worker = _FakeWorker()
        references = tuple(
            KieReferenceImage(
                telegram_file_id=f"file-{index}",
                telegram_file_unique_id=f"unique-{index}",
                source="upload",
                file_name=f"reference-{index}.jpg",
            )
            for index in range(5)
        )
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt="test",
            references=references,
        )
        task = SimpleNamespace(payload={})

        prepared = await _fast_upload_references(
            worker,
            queue_task_id="queue-id",
            request=request,
            task=task,
            progress=None,
        )

        self.assertEqual(5, worker.download_calls)
        self.assertEqual(5, worker.upload_calls)
        self.assertGreater(worker.max_active_downloads, 1)
        self.assertLessEqual(worker.max_active_downloads, 3)
        self.assertEqual(1, worker._queue.heartbeats)
        self.assertEqual(
            tuple(
                f"https://files.invalid/queue-id-{index + 1}-reference-{index}.jpg"
                for index in range(5)
            ),
            prepared.image_urls,
        )

    async def test_recent_reference_urls_are_reused_without_uploading_again(self) -> None:
        worker = _FakeWorker()
        reference = KieReferenceImage(
            telegram_file_id="file-1",
            telegram_file_unique_id="unique-1",
            source="upload",
            file_name="reference.jpg",
        )
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt="test",
            references=(reference,),
        )
        task = SimpleNamespace(payload={})

        first = await _fast_upload_references(
            worker,
            queue_task_id="first",
            request=request,
            task=task,
            progress=None,
        )
        second = await _fast_upload_references(
            worker,
            queue_task_id="second",
            request=request,
            task=task,
            progress=None,
        )

        self.assertEqual(1, worker.download_calls)
        self.assertEqual(1, worker.upload_calls)
        self.assertEqual(first.image_urls, second.image_urls)


class GrsBalancePriceTests(unittest.TestCase):
    def test_grs_screen_uses_grs_model_prices_not_kie_credit_price(self) -> None:
        text = _render_grs_balance(
            credits=Decimal("3000"),
            balance_error=None,
            nano_banana_2_usd=Decimal("0.02"),
            nano_banana_pro_usd=Decimal("0.03"),
            usd_to_rub=Decimal("100"),
        )

        self.assertIn("0.0200 $ · 2.00 ₽", text)
        self.assertIn("0.0300 $ · 3.00 ₽", text)
        self.assertIn("0.0500 $ · 5.00 ₽", text)
        self.assertNotIn("9.00 $", text)


if __name__ == "__main__":
    unittest.main()

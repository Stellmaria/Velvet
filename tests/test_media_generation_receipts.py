from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from velvet_bot.app.media_generation_receipts import (
    _ReceiptContext,
    _aggregate_delivery_status,
    _deliver_with_receipt,
    _duration_text,
    _extract_attempt,
    _extract_consumed_credits,
    _extract_provider_task_id,
    _provider_latency_ms,
)
from velvet_bot.domains.ai_usage import AITask, AITaskStatus
from velvet_bot.domains.media_generation import (
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KiePricing,
    KieReferenceImage,
    KieTaskRecord,
    KieTaskState,
)


class ReceiptParsingTests(unittest.TestCase):
    def test_extracts_paid_attempt_and_provider_task_id(self) -> None:
        stage = "Kie принял попытку 2/5: b5da73b5ecb521095056d92159cf4f0c."
        self.assertEqual((2, 5), _extract_attempt(stage))
        self.assertEqual(
            "b5da73b5ecb521095056d92159cf4f0c",
            _extract_provider_task_id(stage),
        )

    def test_extracts_nested_consumed_credits(self) -> None:
        self.assertEqual(
            Decimal("116"),
            _extract_consumed_credits(
                {"data": {"billing": {"creditsConsumed": "116"}}}
            ),
        )

    def test_provider_latency_prefers_cost_time(self) -> None:
        record = KieTaskRecord(
            task_id="provider-1",
            state=KieTaskState.SUCCESS,
            raw={"costTime": 107000},
        )
        self.assertEqual(107000, _provider_latency_ms(record))
        self.assertEqual("1 мин 47 сек", _duration_text(107000))

    def test_delivery_status_is_aggregated(self) -> None:
        self.assertEqual("sent", _aggregate_delivery_status([True, True]))
        self.assertEqual("partial", _aggregate_delivery_status([True, False]))
        self.assertEqual("failed", _aggregate_delivery_status([False]))
        self.assertEqual("not_sent", _aggregate_delivery_status([]))


class ReceiptDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def _task(self, request: KieGenerationRequest) -> AITask:
        return AITask(
            id=uuid4(),
            scope=SimpleNamespace(value="vision"),
            task_type="media.generate.kie",
            status=AITaskStatus.RUNNING,
            priority=100,
            payload={"chat_id": 100},
            result={},
            dedupe_key=None,
            attempt_count=1,
            max_attempts=3,
            not_before=datetime.now(timezone.utc),
            locked_by="test",
            locked_at=datetime.now(timezone.utc),
            last_error_type=None,
            last_error=None,
            last_retry_delay_seconds=None,
            estimated_cost_rub=Decimal("1"),
            created_by=1,
            created_at=datetime.now(timezone.utc) - timedelta(seconds=123),
            updated_at=datetime.now(timezone.utc),
            completed_at=None,
        )

    def _worker(self, request: KieGenerationRequest, *, document_error=None):
        bot = SimpleNamespace(
            send_document=AsyncMock(side_effect=document_error),
            send_video=AsyncMock(),
            send_photo=AsyncMock(),
            send_message=AsyncMock(),
        )

        async def retry(_name, operation):
            return await operation()

        task = self._task(request)
        context = _ReceiptContext(
            task=task,
            request=request,
            started_monotonic=0.0,
            provider_started_monotonic=None,
            provider_attempt=1,
            max_attempts=3,
            provider_task_id="provider-1",
        )
        worker = SimpleNamespace(
            _bot=bot,
            _download_result=AsyncMock(
                return_value=SimpleNamespace(
                    payload=b"media-bytes",
                    mime_type="video/mp4" if request.model.is_video else "image/png",
                )
            ),
            _send_telegram_with_retry=retry,
            _pricing=KiePricing(),
            _usd_to_rub=Decimal("90"),
            _provider_balances={},
            _client=SimpleNamespace(
                get_grs_credits=AsyncMock(return_value=Decimal("0")),
                models=SimpleNamespace(
                    provider_model_for_request=lambda _request: "provider/model"
                ),
            ),
            _media_receipt_by_queue={str(task.id): context},
            _media_receipt_by_provider={"provider-1": context},
            _campaign_queue=SimpleNamespace(),
        )
        return worker, bot

    async def test_grok_15_sends_original_document_and_video_preview(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.GROK_IMAGINE_VIDEO_15,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt="camera movement",
            references=(
                KieReferenceImage(
                    telegram_file_id="file",
                    source="upload",
                    file_name="ref.jpg",
                ),
            ),
            image_urls=("https://cdn.example/reference.jpg",),
            resolution="480p",
            duration_seconds=6,
        )
        worker, bot = self._worker(request)
        record = KieTaskRecord(
            task_id="provider-1",
            state=KieTaskState.SUCCESS,
            result_urls=("https://cdn.example/result",),
            consumed_credits=116,
            raw={"costTime": 107000},
        )

        await _deliver_with_receipt(
            worker,
            chat_id=100,
            request=request,
            record=record,
        )

        bot.send_document.assert_awaited_once()
        bot.send_video.assert_awaited_once()
        bot.send_photo.assert_not_awaited()
        document_kwargs = bot.send_document.await_args.kwargs
        self.assertIs(True, document_kwargs["disable_content_type_detection"])
        receipt = bot.send_message.await_args_list[0].args[1]
        self.assertIn("Списано: <b>116 кредитов</b>", receipt)
        self.assertIn("Генерация у провайдера: <b>1 мин 47 сек</b>", receipt)
        self.assertIn("Успешная попытка: <b>1/3</b>", receipt)
        self.assertIn("Оригинальный файл: <b>отправлен</b>", receipt)

    async def test_document_failure_does_not_hide_preview_or_warning(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.GROK_IMAGINE_VIDEO_15,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt="camera movement",
            references=(
                KieReferenceImage(
                    telegram_file_id="file",
                    source="upload",
                    file_name="ref.jpg",
                ),
            ),
            image_urls=("https://cdn.example/reference.jpg",),
            resolution="480p",
            duration_seconds=6,
        )
        worker, bot = self._worker(request, document_error=RuntimeError("upload failed"))
        record = KieTaskRecord(
            task_id="provider-1",
            state=KieTaskState.SUCCESS,
            result_urls=("https://cdn.example/result.mp4",),
        )

        await _deliver_with_receipt(
            worker,
            chat_id=100,
            request=request,
            record=record,
        )

        bot.send_video.assert_awaited_once()
        self.assertGreaterEqual(bot.send_message.await_count, 2)
        receipt = bot.send_message.await_args_list[0].args[1]
        warning = bot.send_message.await_args_list[1].args[1]
        self.assertIn("Оригинальный файл: <b>ошибка</b>", receipt)
        self.assertIn("Часть результата не доставлена", warning)

    async def test_every_photo_alias_sends_document_and_photo_preview(self) -> None:
        aliases = (
            KieModelAlias.SEEDREAM_5_PRO,
            KieModelAlias.NANO_BANANA_2,
            KieModelAlias.NANO_BANANA_PRO,
            KieModelAlias.QWEN2_IMAGE_EDIT,
            KieModelAlias.WAN_27_IMAGE,
            KieModelAlias.FLUX_2_PRO_IMAGE,
        )
        for alias in aliases:
            with self.subTest(alias=alias):
                request = KieGenerationRequest(
                    model=alias,
                    input_mode=KieInputMode.PHOTO_TEXT,
                    prompt="edit",
                    references=(
                        KieReferenceImage(
                            telegram_file_id="file",
                            source="upload",
                            file_name="ref.jpg",
                        ),
                    ),
                    image_urls=("https://cdn.example/reference.jpg",),
                    resolution=alias.supported_photo_resolutions[0],
                    aspect_ratio=alias.default_photo_aspect_ratio,
                )
                worker, bot = self._worker(request)
                record = KieTaskRecord(
                    task_id="provider-1",
                    state=KieTaskState.SUCCESS,
                    result_urls=("https://cdn.example/result.png",),
                )
                await _deliver_with_receipt(
                    worker,
                    chat_id=100,
                    request=request,
                    record=record,
                )
                bot.send_document.assert_awaited_once()
                bot.send_photo.assert_awaited_once()
                bot.send_video.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

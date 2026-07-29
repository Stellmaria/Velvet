from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import BufferedInputFile

from velvet_bot.domains.media_generation import (
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KiePricing,
    KieTaskRecord,
    KieTaskState,
)
from velvet_bot.domains.media_generation.friendly_worker import (
    FriendlyKieGenerationWorker,
)


class FriendlyGrsFileDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_grs_result_is_downloaded_then_sent_as_preview_and_document(self) -> None:
        bot = SimpleNamespace(
            send_photo=AsyncMock(),
            send_document=AsyncMock(),
            send_video=AsyncMock(),
            send_message=AsyncMock(),
        )
        worker = FriendlyKieGenerationWorker(
            bot=bot,
            queue=SimpleNamespace(),
            client=SimpleNamespace(user_agent="Velvet-Test/1.0"),
            executor=SimpleNamespace(),
            pricing=KiePricing(),
            usd_to_rub=Decimal("100"),
        )
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            input_mode=KieInputMode.TEXT,
            prompt="portrait",
            resolution="2K",
        )
        record = KieTaskRecord(
            task_id="grs-provider-123",
            state=KieTaskState.SUCCESS,
            result_urls=("https://cdn.example/generated-image",),
        )
        downloaded = SimpleNamespace(
            payload=b"original-grs-image",
            mime_type="image/png",
        )

        with patch.object(
            worker,
            "_download_result",
            AsyncMock(return_value=downloaded),
        ):
            await worker._deliver_best_effort(
                chat_id=100,
                request=request,
                record=record,
            )

        bot.send_photo.assert_awaited_once()
        bot.send_document.assert_awaited_once()
        bot.send_video.assert_not_awaited()

        photo_call = bot.send_photo.await_args
        preview = photo_call.kwargs["photo"]
        self.assertIsInstance(preview, BufferedInputFile)
        self.assertEqual(b"original-grs-image", preview.data)
        self.assertIn("Провайдер: <b>GRS AI</b>", photo_call.kwargs["caption"])
        self.assertIn("предпросмотр и оригинальный файл", photo_call.kwargs["caption"])

        document_call = bot.send_document.await_args
        original = document_call.kwargs["document"]
        self.assertIsInstance(original, BufferedInputFile)
        self.assertEqual(b"original-grs-image", original.data)
        self.assertEqual(
            "Оригинальный файл изображения.",
            document_call.kwargs["caption"],
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

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
    async def test_generation_worker_never_delivers_provider_result_directly(self) -> None:
        bot = SimpleNamespace(
            send_photo=AsyncMock(),
            send_document=AsyncMock(),
            send_video=AsyncMock(),
            send_message=AsyncMock(),
        )
        queue = SimpleNamespace(
            database=object(),
            configure_durable_delivery=Mock(),
        )
        runtime = SimpleNamespace(
            resolver=object(),
            delivery=object(),
            recover_once=AsyncMock(),
        )
        worker = FriendlyKieGenerationWorker(
            bot=bot,
            queue=queue,
            client=SimpleNamespace(user_agent="Velvet-Test/1.0"),
            executor=SimpleNamespace(),
            pricing=KiePricing(),
            usd_to_rub=Decimal("100"),
            media_delivery_runtime=runtime,
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

        await worker._deliver_best_effort(
            chat_id=100,
            request=request,
            record=record,
        )

        queue.configure_durable_delivery.assert_called_once_with(
            resolver=runtime.resolver,
            delivery=runtime.delivery,
        )
        bot.send_photo.assert_not_awaited()
        bot.send_document.assert_not_awaited()
        bot.send_video.assert_not_awaited()
        bot.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

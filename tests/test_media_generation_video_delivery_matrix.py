from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.app.media_generation_receipts import _deliver_with_receipt
from velvet_bot.domains.media_generation import (
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KiePricing,
    KieReferenceImage,
    KieTaskRecord,
    KieTaskState,
)


class MediaGenerationVideoDeliveryMatrixTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_video_alias_sends_original_document_and_preview(self) -> None:
        aliases = (
            KieModelAlias.GROK_IMAGINE_VIDEO,
            KieModelAlias.GROK_IMAGINE_VIDEO_15,
            KieModelAlias.SEEDANCE_15_PRO_VIDEO,
            KieModelAlias.WAN_26_IMAGE_TO_VIDEO,
        )
        for alias in aliases:
            with self.subTest(alias=alias):
                request = KieGenerationRequest(
                    model=alias,
                    input_mode=KieInputMode.PHOTO_TEXT,
                    prompt="subtle camera movement",
                    references=(
                        KieReferenceImage(
                            telegram_file_id="file",
                            source="upload",
                            file_name="reference.jpg",
                        ),
                    ),
                    image_urls=("https://cdn.example/reference.jpg",),
                    resolution="480p",
                    duration_seconds=6,
                )
                bot = SimpleNamespace(
                    send_document=AsyncMock(),
                    send_video=AsyncMock(),
                    send_photo=AsyncMock(),
                    send_message=AsyncMock(),
                )

                async def retry(_name, operation):
                    return await operation()

                worker = SimpleNamespace(
                    _bot=bot,
                    _download_result=AsyncMock(
                        return_value=SimpleNamespace(
                            payload=b"original-video-bytes",
                            mime_type="video/mp4",
                        )
                    ),
                    _send_telegram_with_retry=retry,
                    _pricing=KiePricing(),
                    _usd_to_rub=Decimal("90"),
                    _provider_balances={},
                    _client=SimpleNamespace(
                        models=SimpleNamespace(
                            provider_model_for_request=lambda _request: "provider/video"
                        )
                    ),
                    _media_receipt_by_queue={},
                    _media_receipt_by_provider={},
                    _campaign_queue=SimpleNamespace(),
                )
                record = KieTaskRecord(
                    task_id=f"provider-{alias.value}",
                    state=KieTaskState.SUCCESS,
                    result_urls=("https://cdn.example/result",),
                    raw={"costTime": 1000},
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
                self.assertIs(
                    True,
                    bot.send_document.await_args.kwargs[
                        "disable_content_type_detection"
                    ],
                )


if __name__ == "__main__":
    unittest.main()

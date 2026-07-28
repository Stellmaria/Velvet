from __future__ import annotations

import asyncio
import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from velvet_bot.core.config.kie import load_kie_settings
from velvet_bot.domains.media_generation import (
    KieGenerationRequest,
    KieModelAlias,
    KieModelCatalog,
    KiePricing,
    KieTaskState,
)
from velvet_bot.infrastructure.ai import KieClient, KieTaskFailed


class KieMediaProviderTests(unittest.TestCase):
    def test_nano_banana_payload_and_cost(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            prompt="portrait",
            aspect_ratio="9:16",
            resolution="4K",
            image_urls=("https://example.com/ref.png",),
        )
        self.assertEqual(
            {
                "prompt": "portrait",
                "aspect_ratio": "9:16",
                "resolution": "4K",
                "output_format": "png",
                "image_input": ["https://example.com/ref.png"],
            },
            request.to_input(),
        )
        self.assertEqual(Decimal("0.12"), KiePricing().estimate_usd(request))

    def test_grok_video_cost_is_per_second(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.GROK_IMAGINE_VIDEO,
            prompt="slow camera movement",
            resolution="720p",
            duration_seconds=10,
        )
        self.assertEqual(Decimal("0.150"), KiePricing().estimate_usd(request))

    def test_client_create_and_wait(self) -> None:
        calls: list[tuple[str, str, object]] = []
        responses = iter(
            [
                {"code": 200, "msg": "success", "data": {"taskId": "task-1"}},
                {
                    "code": 200,
                    "msg": "success",
                    "data": {"taskId": "task-1", "state": "generating"},
                },
                {
                    "code": 200,
                    "msg": "success",
                    "data": {
                        "taskId": "task-1",
                        "state": "success",
                        "consumeCredits": 18,
                        "resultJson": '{"resultUrls":["https://cdn/result.png"]}',
                    },
                },
            ]
        )

        def transport(method, url, headers, payload, timeout):
            calls.append((method, url, payload))
            self.assertEqual("Bearer secret", headers["Authorization"])
            self.assertEqual(5, timeout)
            return next(responses)

        client = KieClient(
            api_key="secret",
            models=KieModelCatalog(seedream_5_pro="seedream/test"),
            timeout_seconds=5,
            poll_interval_seconds=1,
            task_timeout_seconds=10,
            transport=transport,
        )
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            prompt="portrait",
        )

        async def scenario():
            task_id = await client.create_task(request)
            return await client.wait_for_task(task_id)

        with patch("velvet_bot.infrastructure.ai.kie.asyncio.sleep", return_value=None):
            record = asyncio.run(scenario())
        self.assertEqual(KieTaskState.SUCCESS, record.state)
        self.assertEqual(("https://cdn/result.png",), record.result_urls)
        self.assertEqual(18, record.consumed_credits)
        self.assertEqual("nano-banana-pro", calls[0][2]["model"])

    def test_failed_task_raises_typed_error(self) -> None:
        def transport(method, url, headers, payload, timeout):
            return {
                "code": 200,
                "data": {
                    "taskId": "task-bad",
                    "state": "fail",
                    "failCode": "422",
                    "failMsg": "rejected",
                },
            }

        client = KieClient(
            api_key="secret",
            models=KieModelCatalog(seedream_5_pro="seedream/test"),
            transport=transport,
            poll_interval_seconds=1,
        )
        with self.assertRaises(KieTaskFailed):
            asyncio.run(client.wait_for_task("task-bad"))

    def test_settings_require_key_and_seedream_model_when_enabled(self) -> None:
        base = {
            "KIE_ENABLED": "true",
            "KIE_API_KEY": "secret",
        }
        with patch.dict(os.environ, base, clear=True), patch(
            "velvet_bot.core.config.kie.load_dotenv"
        ):
            with self.assertRaisesRegex(RuntimeError, "model id"):
                load_kie_settings()

    def test_settings_load_documented_model_defaults(self) -> None:
        values = {
            "KIE_ENABLED": "true",
            "KIE_API_KEY": "secret",
            "KIE_SEEDREAM_5_PRO_MODEL": "seedream/5-pro-text-to-image",
        }
        with patch.dict(os.environ, values, clear=True), patch(
            "velvet_bot.core.config.kie.load_dotenv"
        ):
            settings = load_kie_settings()
        self.assertEqual("nano-banana-pro", settings.models.nano_banana_pro)
        self.assertEqual(
            "grok-imagine/text-to-video",
            settings.models.grok_imagine_video,
        )
        self.assertEqual(Decimal("0.09"), settings.pricing.nano_1k_2k_usd)


if __name__ == "__main__":
    unittest.main()

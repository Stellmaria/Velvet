from __future__ import annotations

import asyncio
import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from velvet_bot.core.config.kie import load_kie_settings
from velvet_bot.domains.media_generation import (
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KieModelCatalog,
    KiePricing,
    KieReferenceImage,
    KieTaskState,
)
from velvet_bot.infrastructure.ai import KieClient, KieTaskFailed
from velvet_bot.presentation.telegram.routers.workspace_auf_grs import (
    build_model_keyboard,
    model_selection_text,
)


def _reference() -> KieReferenceImage:
    return KieReferenceImage(
        telegram_file_id="telegram-file",
        source="upload",
        mime_type="image/jpeg",
        file_name="reference.jpg",
    )


def _labels(keyboard) -> list[str]:
    return [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]


class GrsMediaProviderTests(unittest.TestCase):
    def test_banana_2_builds_documented_unified_payload(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_2,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt="portrait",
            references=(_reference(),),
            aspect_ratio="9:16",
            resolution="4K",
        ).with_image_urls(("https://example.com/reference.jpg",))

        self.assertEqual(
            {
                "model": "nano-banana-2",
                "prompt": "portrait",
                "images": ["https://example.com/reference.jpg"],
                "aspectRatio": "9:16",
                "imageSize": "4K",
                "replyType": "json",
            },
            request.to_grs_input(model_id="nano-banana-2"),
        )
        self.assertEqual(
            ("1K", "2K", "4K"),
            KieModelAlias.NANO_BANANA_2.supported_photo_resolutions,
        )
        self.assertEqual(Decimal("0.02"), KiePricing().estimate_usd(request))

    def test_grs_immediate_success_uses_generate_response_without_extra_poll(self) -> None:
        calls: list[tuple[str, str, dict[str, str], object]] = []

        def transport(method, url, headers, payload, timeout):
            calls.append((method, url, dict(headers), payload))
            return {
                "id": "14-task-1",
                "status": "succeeded",
                "results": [{"url": "https://cdn.example/result.png"}],
            }

        client = KieClient(
            api_key="kie-secret",
            grs_api_key="grs-secret",
            grs_base_url="https://grs.example",
            models=KieModelCatalog(),
            transport=transport,
        )
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            input_mode=KieInputMode.TEXT,
            prompt="portrait",
            resolution="2K",
        )

        async def scenario():
            task_id = await client.create_task(request)
            return task_id, await client.wait_for_task(task_id)

        task_id, record = asyncio.run(scenario())
        self.assertEqual("grs:14-task-1", task_id)
        self.assertEqual(KieTaskState.SUCCESS, record.state)
        self.assertEqual(("https://cdn.example/result.png",), record.result_urls)
        self.assertEqual(1, len(calls))
        self.assertEqual("POST", calls[0][0])
        self.assertEqual("https://grs.example/v1/api/generate", calls[0][1])
        self.assertEqual("Bearer grs-secret", calls[0][2]["Authorization"])
        self.assertEqual("nano-banana-pro", calls[0][3]["model"])

    def test_grs_async_task_polls_result_endpoint(self) -> None:
        responses = iter(
            [
                {"id": "14-task-2", "status": "submitted", "results": []},
                {
                    "id": "14-task-2",
                    "status": "succeeded",
                    "results": [{"url": "https://cdn.example/final.png"}],
                },
            ]
        )
        calls: list[tuple[str, str]] = []

        def transport(method, url, headers, payload, timeout):
            calls.append((method, url))
            return next(responses)

        client = KieClient(
            api_key="kie-secret",
            grs_api_key="grs-secret",
            grs_base_url="https://grs.example",
            models=KieModelCatalog(),
            poll_interval_seconds=1,
            transport=transport,
        )
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_2,
            input_mode=KieInputMode.TEXT,
            prompt="portrait",
            resolution="1K",
        )

        async def scenario():
            task_id = await client.create_task(request)
            return await client.wait_for_task(task_id)

        with patch("velvet_bot.infrastructure.ai.kie.asyncio.sleep", return_value=None):
            record = asyncio.run(scenario())
        self.assertEqual(KieTaskState.SUCCESS, record.state)
        self.assertEqual(
            ("GET", "https://grs.example/v1/api/result?id=14-task-2"),
            calls[1],
        )

    def test_grs_failed_status_raises_existing_typed_task_error(self) -> None:
        def transport(method, url, headers, payload, timeout):
            return {
                "id": "14-task-bad",
                "status": "failed",
                "error": {"code": "422", "message": "rejected"},
            }

        client = KieClient(
            api_key="kie-secret",
            grs_api_key="grs-secret",
            models=KieModelCatalog(),
            transport=transport,
        )
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_2,
            input_mode=KieInputMode.TEXT,
            prompt="portrait",
            resolution="1K",
        )

        async def scenario():
            task_id = await client.create_task(request)
            return await client.wait_for_task(task_id)

        with self.assertRaisesRegex(KieTaskFailed, "GRS AI"):
            asyncio.run(scenario())

    def test_meow_exposes_both_grs_bananas_and_keeps_seedream(self) -> None:
        self.assertEqual(
            [
                "Nano Banana 2",
                "Nano Banana Pro",
                "Seedream 5 Pro",
                "↩️ К проверке",
                "Отмена",
            ],
            _labels(build_model_keyboard(workspace_id=9)),
        )
        text = model_selection_text()
        self.assertIn("GRS AI", text)
        self.assertIn("Kie.ai", text)

    def test_settings_load_grs_endpoint_models_and_budget_estimates(self) -> None:
        values = {
            "KIE_ENABLED": "true",
            "KIE_API_KEY": "kie-secret",
            "GRS_API_KEY": "grs-secret",
            "GRS_BASE_URL": "https://grs.example",
            "KIE_USD_TO_RUB": "100",
            "GRS_NANO_BANANA_2_USD": "0.018",
            "GRS_NANO_BANANA_PRO_USD": "0.027",
        }
        with patch.dict(os.environ, values, clear=True), patch(
            "velvet_bot.core.config.kie.load_dotenv"
        ):
            settings = load_kie_settings()
        self.assertEqual("grs-secret", settings.grs_api_key)
        self.assertEqual("https://grs.example", settings.grs_base_url)
        self.assertEqual("nano-banana-2", settings.models.nano_banana_2)
        self.assertEqual("nano-banana-pro", settings.models.nano_banana_pro)
        self.assertEqual(Decimal("0.018"), settings.pricing.nano_banana_2_usd)
        self.assertEqual(Decimal("0.027"), settings.pricing.nano_banana_pro_usd)


if __name__ == "__main__":
    unittest.main()

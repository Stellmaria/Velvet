from __future__ import annotations

import asyncio
import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from velvet_bot.app import auf_photo_model_modes as modes
from velvet_bot.domains.media_generation import (
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KieModelCatalog,
    KiePricing,
    KieReferenceImage,
)
from velvet_bot.infrastructure.ai import KieClient


def _reference(index: int = 1) -> KieReferenceImage:
    return KieReferenceImage(
        telegram_file_id=f"file-{index}",
        telegram_file_unique_id=f"unique-{index}",
        source="upload",
        mime_type="image/jpeg",
        file_name=f"reference-{index}.jpg",
        file_size=1024,
    )


class AufPhotoModelModeTests(unittest.TestCase):
    def test_model_cards_show_exact_limits_and_file_size(self) -> None:
        expected = {
            KieModelAlias.SEEDREAM_5_PRO: (10, 8000),
            KieModelAlias.NANO_BANANA_2: (5, 8000),
            KieModelAlias.NANO_BANANA_PRO: (5, 8000),
            KieModelAlias.WAN_27_IMAGE: (9, 5000),
            KieModelAlias.WAN_27_IMAGE_PRO: (9, 5000),
        }
        for model, (references, prompt) in expected.items():
            with self.subTest(model=model):
                text = modes._model_card(model)
                self.assertIn(f"до {references}", text)
                self.assertIn(f"до {prompt} символов", text)
                self.assertIn("10 МБ", text)
                self.assertIn("только текст", text.casefold())
                self.assertIn("фото + текст", text.casefold())

    def test_retired_qwen_and_flux_are_rejected_by_active_request_builder(self) -> None:
        for model in (
            KieModelAlias.QWEN2_IMAGE_EDIT,
            KieModelAlias.FLUX_2_PRO_IMAGE,
        ):
            with self.subTest(model=model):
                with self.assertRaisesRegex(ValueError, "Сначала выберите модель"):
                    modes._request(
                        {
                            "auf_model": model.value,
                            "auf_input_mode": KieInputMode.PHOTO_TEXT.value,
                            "auf_prompt_parts": ["first part", "second part"],
                            "auf_references": [_reference().to_payload()],
                            "auf_resolution": "2K",
                            "auf_aspect_ratio": "9:16",
                        }
                    )

    def test_active_catalog_contains_only_five_approved_models(self) -> None:
        self.assertEqual(
            (
                KieModelAlias.NANO_BANANA_2,
                KieModelAlias.NANO_BANANA_PRO,
                KieModelAlias.SEEDREAM_5_PRO,
                KieModelAlias.WAN_27_IMAGE_PRO,
                KieModelAlias.WAN_27_IMAGE,
            ),
            modes._PHOTO_MODELS,
        )

    def test_wan_provider_routes_are_distinct(self) -> None:
        catalog = KieModelCatalog()
        self.assertEqual(
            "wan/2-7-image",
            modes._provider_model(
                catalog,
                KieModelAlias.WAN_27_IMAGE,
                input_mode=KieInputMode.TEXT,
            ),
        )
        self.assertEqual(
            "wan/2-7-image-pro",
            modes._provider_model(
                catalog,
                KieModelAlias.WAN_27_IMAGE_PRO,
                input_mode=KieInputMode.TEXT,
            ),
        )

    def test_wan_text_routes_do_not_require_fake_reference(self) -> None:
        for model, resolution in (
            (KieModelAlias.WAN_27_IMAGE, "2K"),
            (KieModelAlias.WAN_27_IMAGE_PRO, "4K"),
        ):
            with self.subTest(model=model):
                request = KieGenerationRequest(
                    model=model,
                    input_mode=KieInputMode.TEXT,
                    prompt="text only",
                    resolution=resolution,
                    aspect_ratio="9:16",
                )
                payload = modes._to_input(request)
                self.assertNotIn("input_urls", payload)

    def test_seedream_output_format_is_selected_only_for_seedream(self) -> None:
        seedream = modes._request(
            {
                "auf_model": KieModelAlias.SEEDREAM_5_PRO.value,
                "auf_input_mode": KieInputMode.TEXT.value,
                "auf_prompt_parts": ["portrait"],
                "auf_resolution": "2K",
                "auf_aspect_ratio": "9:16",
                "auf_output_format": "jpeg",
            }
        )
        self.assertEqual("jpeg", seedream.output_format)

        wan = modes._request(
            {
                "auf_model": KieModelAlias.WAN_27_IMAGE.value,
                "auf_input_mode": KieInputMode.TEXT.value,
                "auf_prompt_parts": ["portrait"],
                "auf_resolution": "1K",
                "auf_aspect_ratio": "9:16",
                "auf_output_format": "jpeg",
            }
        )
        self.assertEqual("png", wan.output_format)

    def test_wan_n_and_sequential_are_the_only_advanced_controls(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.WAN_27_IMAGE,
            input_mode=KieInputMode.TEXT,
            prompt="connected storyboard",
            resolution="2K",
            aspect_ratio="16:9",
            extra_input={"n": 6, "enable_sequential": True},
        )
        payload = modes._to_input(request)
        self.assertEqual(6, payload["n"])
        self.assertIs(True, payload["enable_sequential"])
        self.assertNotIn("input_urls", payload)
        for forbidden in (
            "thinking_mode",
            "watermark",
            "seed",
            "bbox_list",
            "callBackUrl",
        ):
            self.assertNotIn(forbidden, payload)

        cost = modes._estimate_usd(KiePricing(), request)
        self.assertEqual(Decimal("0.18"), cost)

    def test_wan_non_sequential_count_is_clamped_to_four(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.WAN_27_IMAGE,
            input_mode=KieInputMode.TEXT,
            prompt="variants",
            resolution="1K",
            aspect_ratio="1:1",
            extra_input={"n": 12, "enable_sequential": False},
        )
        payload = modes._to_input(request)
        self.assertEqual(4, payload["n"])

    def test_banana_pro_uses_vt_then_regular_after_explicit_failure(self) -> None:
        calls: list[tuple[str, str, object]] = []
        primary_poll_count = 0

        def transport(method, url, headers, payload, timeout):
            nonlocal primary_poll_count
            calls.append((method, url, payload))
            if method == "POST":
                model = payload["model"]
                if model == "nano-banana-pro-vt":
                    return {"id": "vt-task", "status": "submitted", "results": []}
                if model == "nano-banana-pro":
                    return {
                        "id": "regular-task",
                        "status": "succeeded",
                        "results": [{"url": "https://cdn.example/result.png"}],
                    }
            if method == "GET" and "vt-task" in url:
                primary_poll_count += 1
                return {
                    "id": "vt-task",
                    "status": "failed",
                    "error": {"code": "provider_failed", "message": "rejected"},
                }
            raise AssertionError((method, url, payload))

        client = KieClient(
            api_key="kie-secret",
            grs_api_key="grs-secret",
            grs_base_url="https://grs.example",
            models=KieModelCatalog(nano_banana_pro="nano-banana-pro-vt"),
            poll_interval_seconds=1,
            transport=transport,
        )
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            input_mode=KieInputMode.TEXT,
            prompt="portrait",
            resolution="2K",
            aspect_ratio="9:16",
        )

        async def scenario():
            task_id = await modes._create_grs_with_vt_fallback(client, request)
            return await modes._wait_with_vt_fallback(client, task_id)

        with patch.dict(
            os.environ,
            {"GRS_NANO_BANANA_PRO_FALLBACK_MODEL": "nano-banana-pro"},
            clear=False,
        ), patch(
            "velvet_bot.infrastructure.ai.kie.asyncio.sleep",
            return_value=None,
        ):
            record = asyncio.run(scenario())

        posted_models = [
            payload["model"]
            for method, _, payload in calls
            if method == "POST" and isinstance(payload, dict)
        ]
        self.assertEqual(
            ["nano-banana-pro-vt", "nano-banana-pro"],
            posted_models,
        )
        self.assertEqual(
            ("https://cdn.example/result.png",),
            record.result_urls,
        )
        self.assertEqual(1, primary_poll_count)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import asyncio
import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from velvet_bot.core.config.kie import load_kie_settings
from velvet_bot.domains.media_generation import (
    KieContentMode,
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KieModelCatalog,
    KiePricing,
    KieReferenceImage,
    KieTaskState,
)
from velvet_bot.infrastructure.ai import KieClient, KieTaskFailed


def _reference(*, source: str = "library") -> KieReferenceImage:
    return KieReferenceImage(
        telegram_file_id="telegram-file",
        telegram_file_unique_id="telegram-unique",
        source=source,
        mime_type="image/jpeg",
        file_name="reference.jpg",
        file_size=1024,
        character_id=7 if source == "library" else None,
        reference_id=11 if source == "library" else None,
    )


class KieMediaProviderTests(unittest.TestCase):
    def test_nano_banana_reference_payload_and_cost(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt="portrait",
            references=(_reference(),),
            aspect_ratio="9:16",
            resolution="4K",
        ).with_image_urls(("https://example.com/ref.png",))
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
        pricing = KiePricing()
        self.assertEqual(Decimal("0.12"), pricing.estimate_usd(request))
        self.assertEqual(
            Decimal("12.00"),
            pricing.estimate_rub(request, usd_to_rub=Decimal("100")),
        )

    def test_seedream_mature_disables_documented_nsfw_checker(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.SEEDREAM_5_PRO,
            input_mode=KieInputMode.PHOTO,
            references=(_reference(),),
            content_mode=KieContentMode.MATURE,
            resolution="2K",
        ).with_image_urls(("https://example.com/ref.jpg",))
        payload = request.to_input()
        self.assertEqual("high", payload["quality"])
        self.assertEqual(["https://example.com/ref.jpg"], payload["image_urls"])
        self.assertEqual("png", payload["output_format"])
        self.assertIs(False, payload["nsfw_checker"])
        self.assertTrue(str(payload["prompt"]).strip())
        self.assertEqual(Decimal("0.15"), KiePricing().estimate_usd(request))

    def test_seedream_text_payload_omits_image_urls(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.SEEDREAM_5_PRO,
            input_mode=KieInputMode.TEXT,
            prompt="portrait",
            content_mode=KieContentMode.MATURE,
            resolution="1K",
        )
        payload = request.to_input()
        self.assertNotIn("image_urls", payload)
        self.assertEqual("basic", payload["quality"])
        self.assertIs(False, payload["nsfw_checker"])

    def test_seedream_catalog_routes_text_and_image_endpoints(self) -> None:
        catalog = KieModelCatalog(
            seedream_5_pro_text="seedream/5-pro-text-to-image",
            seedream_5_pro_image="seedream/5-pro-image-to-image",
        )
        self.assertEqual(
            "seedream/5-pro-text-to-image",
            catalog.provider_model(
                KieModelAlias.SEEDREAM_5_PRO,
                input_mode=KieInputMode.TEXT,
            ),
        )
        self.assertEqual(
            "seedream/5-pro-image-to-image",
            catalog.provider_model(
                KieModelAlias.SEEDREAM_5_PRO,
                input_mode=KieInputMode.PHOTO_TEXT,
            ),
        )

    def test_photo_models_expose_only_supported_quality(self) -> None:
        self.assertEqual(
            ("1K", "2K", "4K"),
            KieModelAlias.NANO_BANANA_PRO.supported_photo_resolutions,
        )
        self.assertEqual(
            ("1K", "2K"),
            KieModelAlias.SEEDREAM_5_PRO.supported_photo_resolutions,
        )
        with self.assertRaisesRegex(ValueError, "не поддерживает качество"):
            KieGenerationRequest(
                model=KieModelAlias.SEEDREAM_5_PRO,
                input_mode=KieInputMode.TEXT,
                prompt="portrait",
                resolution="4K",
            )

    def test_grok_video_cost_is_per_second(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.GROK_IMAGINE_VIDEO,
            input_mode=KieInputMode.TEXT,
            prompt="slow camera movement",
            resolution="720p",
            duration_seconds=10,
        )
        self.assertEqual(Decimal("0.150"), KiePricing().estimate_usd(request))

    def test_queue_payload_roundtrip_preserves_references_and_content_mode(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt="camera portrait",
            references=(_reference(), _reference(source="upload")),
            content_mode=KieContentMode.MATURE,
            aspect_ratio="9:16",
            resolution="2K",
            extra_input={"seed": 42},
        )
        restored = KieGenerationRequest.from_task_payload(request.to_task_payload())
        self.assertEqual(request, restored)
        self.assertEqual(2, len(restored.references))
        self.assertEqual(KieContentMode.MATURE, restored.content_mode)
        self.assertEqual("Nano Banana Pro", restored.model.display_name)

    def test_client_uploads_reference_with_base64_api(self) -> None:
        calls: list[tuple[str, str, object]] = []

        def transport(method, url, headers, payload, timeout):
            calls.append((method, url, payload))
            self.assertEqual("Bearer secret", headers["Authorization"])
            return {
                "success": True,
                "data": {
                    "downloadUrl": "https://temp.example/reference.jpg",
                    "fileName": "reference.jpg",
                    "mimeType": "image/jpeg",
                    "fileSize": 3,
                },
            }

        client = KieClient(
            api_key="secret",
            models=KieModelCatalog(
                seedream_5_pro_image="seedream/5-pro-image-to-image"
            ),
            file_upload_base_url="https://upload.example",
            transport=transport,
        )
        uploaded = asyncio.run(
            client.upload_reference(
                b"abc",
                mime_type="image/jpeg",
                file_name="../reference.jpg",
            )
        )
        self.assertEqual("https://temp.example/reference.jpg", uploaded.file_url)
        self.assertEqual("POST", calls[0][0])
        self.assertEqual(
            "https://upload.example/api/file-base64-upload",
            calls[0][1],
        )
        request_payload = calls[0][2]
        self.assertIsInstance(request_payload, dict)
        self.assertEqual("reference.jpg", request_payload["fileName"])
        self.assertTrue(str(request_payload["base64Data"]).startswith("data:image/jpeg;base64,"))

    def test_client_create_wait_and_progress_callback(self) -> None:
        calls: list[tuple[str, str, object]] = []
        updates: list[tuple[KieTaskState, int]] = []
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
                        "creditsConsumed": 18,
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
            models=KieModelCatalog(),
            timeout_seconds=5,
            poll_interval_seconds=1,
            task_timeout_seconds=10,
            transport=transport,
        )
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_PRO,
            input_mode=KieInputMode.TEXT,
            prompt="portrait",
            resolution="1K",
        )

        async def scenario():
            async def on_update(record, poll_count):
                updates.append((record.state, poll_count))

            task_id = await client.create_task(request)
            return await client.wait_for_task(task_id, on_update=on_update)

        with patch("velvet_bot.infrastructure.ai.kie.asyncio.sleep", return_value=None):
            record = asyncio.run(scenario())
        self.assertEqual(KieTaskState.SUCCESS, record.state)
        self.assertEqual(("https://cdn/result.png",), record.result_urls)
        self.assertEqual(18, record.consumed_credits)
        self.assertEqual(
            [(KieTaskState.GENERATING, 1), (KieTaskState.SUCCESS, 2)],
            updates,
        )
        create_payload = calls[0][2]
        self.assertIsInstance(create_payload, dict)
        self.assertEqual("nano-banana-pro", create_payload["model"])

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
            models=KieModelCatalog(),
            transport=transport,
            poll_interval_seconds=1,
        )
        with self.assertRaises(KieTaskFailed):
            asyncio.run(client.wait_for_task("task-bad"))

    def test_settings_require_grs_key_when_enabled(self) -> None:
        values = {
            "KIE_ENABLED": "true",
            "KIE_API_KEY": "secret",
            "KIE_USD_TO_RUB": "100",
        }
        with patch.dict(os.environ, values, clear=True), patch(
            "velvet_bot.core.config.kie.load_dotenv"
        ):
            with self.assertRaisesRegex(RuntimeError, "GRS_API_KEY"):
                load_kie_settings()

    def test_settings_require_budget_rate_when_enabled(self) -> None:
        values = {
            "KIE_ENABLED": "true",
            "KIE_API_KEY": "secret",
            "GRS_API_KEY": "grs-secret",
        }
        with patch.dict(os.environ, values, clear=True), patch(
            "velvet_bot.core.config.kie.load_dotenv"
        ):
            with self.assertRaisesRegex(RuntimeError, "KIE_USD_TO_RUB"):
                load_kie_settings()

    def test_settings_require_both_seedream_routes_when_explicitly_empty(self) -> None:
        base = {
            "KIE_ENABLED": "true",
            "KIE_API_KEY": "secret",
            "GRS_API_KEY": "grs-secret",
            "KIE_USD_TO_RUB": "100",
            "KIE_SEEDREAM_5_PRO_TEXT_MODEL": "",
            "KIE_SEEDREAM_5_PRO_IMAGE_MODEL": "",
        }
        with patch.dict(os.environ, base, clear=True), patch(
            "velvet_bot.core.config.kie.load_dotenv"
        ):
            with self.assertRaisesRegex(RuntimeError, "Seedream 5 Pro"):
                load_kie_settings()

    def test_settings_load_seedream_routes_and_upload_defaults(self) -> None:
        values = {
            "KIE_ENABLED": "true",
            "KIE_API_KEY": "secret",
            "GRS_API_KEY": "grs-secret",
            "KIE_USD_TO_RUB": "100",
        }
        with patch.dict(os.environ, values, clear=True), patch(
            "velvet_bot.core.config.kie.load_dotenv"
        ):
            settings = load_kie_settings()
        self.assertEqual("grs-secret", settings.grs_api_key)
        self.assertEqual("nano-banana-pro", settings.models.nano_banana_pro)
        self.assertEqual(
            "seedream/5-pro-text-to-image",
            settings.models.seedream_5_pro_text,
        )
        self.assertEqual(
            "seedream/5-pro-image-to-image",
            settings.models.seedream_5_pro_image,
        )
        self.assertEqual(
            "https://kieai.redpandaai.co",
            settings.file_upload_base_url,
        )
        self.assertEqual(Decimal("0.09"), settings.pricing.nano_1k_2k_usd)
        self.assertEqual(Decimal("100"), settings.usd_to_rub)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from decimal import Decimal

from velvet_bot.domains.media_generation import (
    KieContentMode,
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
    KiePricing,
    KieReferenceImage,
)


def _references(count: int) -> tuple[KieReferenceImage, ...]:
    return tuple(
        KieReferenceImage(
            telegram_file_id=f"file-{index}",
            telegram_file_unique_id=f"unique-{index}",
            source="upload",
            file_name=f"{index}.jpg",
        )
        for index in range(count)
    )


class PhotoCapabilityMapTests(unittest.TestCase):
    def test_active_image_capabilities_cover_only_approved_models(self) -> None:
        expected = {
            KieModelAlias.SEEDREAM_5_PRO: (10, 8000, ("1K", "2K")),
            KieModelAlias.NANO_BANANA_2: (5, 8000, ("1K", "2K", "4K")),
            KieModelAlias.NANO_BANANA_PRO: (5, 8000, ("1K", "2K", "4K")),
            KieModelAlias.WAN_27_IMAGE: (9, 5000, ("1K", "2K")),
            KieModelAlias.WAN_27_IMAGE_PRO: (9, 5000, ("1K", "2K", "4K")),
        }
        for model, (references, prompt, resolutions) in expected.items():
            with self.subTest(model=model):
                self.assertTrue(model.is_photo_model)
                self.assertEqual(references, model.max_photo_references)
                self.assertEqual(prompt, model.photo_prompt_limit)
                self.assertEqual(resolutions, model.supported_photo_resolutions)
        self.assertFalse(KieModelAlias.QWEN2_IMAGE_EDIT.is_photo_model)
        self.assertFalse(KieModelAlias.FLUX_2_PRO_IMAGE.is_photo_model)

    def test_request_rejects_wan_reference_overflow(self) -> None:
        with self.assertRaisesRegex(ValueError, "принимает не больше 9"):
            KieGenerationRequest(
                model=KieModelAlias.WAN_27_IMAGE,
                input_mode=KieInputMode.PHOTO_TEXT,
                prompt="edit",
                references=_references(10),
                aspect_ratio="9:16",
                resolution="2K",
            )

    def test_wan_pro_4k_is_text_only(self) -> None:
        with self.assertRaisesRegex(ValueError, "4K только"):
            KieGenerationRequest(
                model=KieModelAlias.WAN_27_IMAGE_PRO,
                input_mode=KieInputMode.PHOTO_TEXT,
                prompt="edit",
                references=_references(1),
                aspect_ratio="9:16",
                resolution="4K",
            )
        request = KieGenerationRequest(
            model=KieModelAlias.WAN_27_IMAGE_PRO,
            input_mode=KieInputMode.TEXT,
            prompt="premium poster",
            aspect_ratio="9:16",
            resolution="4K",
        )
        self.assertEqual("4K", request.resolution)

    def test_archive_source_and_workspace_survive_queue_snapshot(self) -> None:
        reference = KieReferenceImage(
            telegram_file_id="system-file",
            source="system",
            character_id=7,
            reference_id=9,
            workspace_id=1,
        )
        restored = KieReferenceImage.from_payload(reference.to_payload())
        self.assertEqual("system", restored.source)
        self.assertEqual(1, restored.workspace_id)
        self.assertEqual(9, restored.reference_id)


class PhotoProviderPayloadTests(unittest.TestCase):
    def test_wan_variants_share_provider_payload_contract(self) -> None:
        for model, resolution in (
            (KieModelAlias.WAN_27_IMAGE, "2K"),
            (KieModelAlias.WAN_27_IMAGE_PRO, "2K"),
        ):
            with self.subTest(model=model):
                request = KieGenerationRequest(
                    model=model,
                    input_mode=KieInputMode.PHOTO_TEXT,
                    prompt="edit only the requested details",
                    references=_references(2),
                    image_urls=(
                        "https://cdn.example/one.jpg",
                        "https://cdn.example/two.jpg",
                    ),
                    content_mode=KieContentMode.MATURE,
                    aspect_ratio="9:16",
                    resolution=resolution,
                )
                payload = request.to_input()
                self.assertEqual(1, payload["n"])
                self.assertIs(False, payload["enable_sequential"])
                self.assertIs(False, payload["thinking_mode"])
                self.assertIs(False, payload["watermark"])
                self.assertIs(False, payload["nsfw_checker"])
                self.assertEqual([[], []], payload["bbox_list"])

    def test_preflight_pricing_is_configurable_per_wan_variant(self) -> None:
        pricing = KiePricing(
            wan_27_1k_usd=Decimal("0.031"),
            wan_27_2k_usd=Decimal("0.032"),
            wan_27_pro_1k_usd=Decimal("0.076"),
            wan_27_pro_2k_usd=Decimal("0.077"),
            wan_27_pro_4k_usd=Decimal("0.078"),
        )
        expected = {
            (KieModelAlias.WAN_27_IMAGE, "1K"): Decimal("0.031"),
            (KieModelAlias.WAN_27_IMAGE, "2K"): Decimal("0.032"),
            (KieModelAlias.WAN_27_IMAGE_PRO, "1K"): Decimal("0.076"),
            (KieModelAlias.WAN_27_IMAGE_PRO, "2K"): Decimal("0.077"),
            (KieModelAlias.WAN_27_IMAGE_PRO, "4K"): Decimal("0.078"),
        }
        for (model, resolution), cost in expected.items():
            request = KieGenerationRequest(
                model=model,
                input_mode=KieInputMode.TEXT,
                prompt="image",
                aspect_ratio="1:1",
                resolution=resolution,
            )
            self.assertEqual(cost, pricing.estimate_usd(request))


if __name__ == "__main__":
    unittest.main()

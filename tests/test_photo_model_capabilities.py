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
    def test_documented_reference_limits_are_model_specific(self) -> None:
        self.assertEqual(10, KieModelAlias.SEEDREAM_5_PRO.max_photo_references)
        self.assertEqual(5, KieModelAlias.NANO_BANANA_2.max_photo_references)
        self.assertEqual(5, KieModelAlias.NANO_BANANA_PRO.max_photo_references)
        self.assertEqual(3, KieModelAlias.QWEN2_IMAGE_EDIT.max_photo_references)
        self.assertEqual(9, KieModelAlias.WAN_27_IMAGE.max_photo_references)
        self.assertEqual(8, KieModelAlias.FLUX_2_PRO_IMAGE.max_photo_references)

    def test_qwen_has_fixed_2k_quality_and_ratio_selection(self) -> None:
        self.assertEqual(
            ("2K",),
            KieModelAlias.QWEN2_IMAGE_EDIT.supported_photo_resolutions,
        )
        self.assertIn(
            "9:16",
            KieModelAlias.QWEN2_IMAGE_EDIT.supported_aspect_ratios,
        )

    def test_wan_and_flux_prompt_limits_match_provider_contract(self) -> None:
        self.assertEqual(5000, KieModelAlias.WAN_27_IMAGE.photo_prompt_limit)
        self.assertEqual(5000, KieModelAlias.FLUX_2_PRO_IMAGE.photo_prompt_limit)

    def test_request_rejects_model_specific_reference_overflow(self) -> None:
        with self.assertRaisesRegex(ValueError, "принимает не больше 3"):
            KieGenerationRequest(
                model=KieModelAlias.QWEN2_IMAGE_EDIT,
                input_mode=KieInputMode.PHOTO_TEXT,
                prompt="edit",
                references=_references(4),
                aspect_ratio="9:16",
                resolution="2K",
            )

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
    def test_qwen_uses_scalar_for_one_reference(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.QWEN2_IMAGE_EDIT,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt="keep the face and change the background",
            references=_references(1),
            image_urls=("https://cdn.example/one.jpg",),
            content_mode=KieContentMode.MATURE,
            aspect_ratio="9:16",
            resolution="2K",
        )
        payload = request.to_input()
        self.assertEqual("https://cdn.example/one.jpg", payload["image_url"])
        self.assertEqual("9:16", payload["image_size"])
        self.assertIs(False, payload["nsfw_checker"])

    def test_qwen_preserves_marketplace_multi_reference_contract(self) -> None:
        urls = tuple(f"https://cdn.example/{index}.jpg" for index in range(3))
        request = KieGenerationRequest(
            model=KieModelAlias.QWEN2_IMAGE_EDIT,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt="combine the references",
            references=_references(3),
            image_urls=urls,
            aspect_ratio="1:1",
            resolution="2K",
        )
        self.assertEqual(list(urls), request.to_input()["image_url"])

    def test_wan_forces_one_output_and_disables_gallery_watermark(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.WAN_27_IMAGE,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt="edit only the requested details",
            references=_references(2),
            image_urls=(
                "https://cdn.example/one.jpg",
                "https://cdn.example/two.jpg",
            ),
            content_mode=KieContentMode.MATURE,
            aspect_ratio="9:16",
            resolution="2K",
        )
        payload = request.to_input()
        self.assertEqual(1, payload["n"])
        self.assertIs(False, payload["enable_sequential"])
        self.assertIs(False, payload["thinking_mode"])
        self.assertIs(False, payload["watermark"])
        self.assertIs(False, payload["nsfw_checker"])
        self.assertEqual([[], []], payload["bbox_list"])

    def test_flux_uses_documented_image_to_image_fields(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.FLUX_2_PRO_IMAGE,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt="move the subject to a night city",
            references=_references(1),
            image_urls=("https://cdn.example/one.jpg",),
            content_mode=KieContentMode.MATURE,
            aspect_ratio="auto",
            resolution="1K",
        )
        payload = request.to_input()
        self.assertEqual(
            ["https://cdn.example/one.jpg"],
            payload["input_urls"],
        )
        self.assertEqual("auto", payload["aspect_ratio"])
        self.assertEqual("1K", payload["resolution"])
        self.assertIs(False, payload["nsfw_checker"])

    def test_preflight_pricing_is_configurable_per_new_model(self) -> None:
        pricing = KiePricing(
            qwen2_image_edit_usd=Decimal("0.021"),
            wan_27_2k_usd=Decimal("0.081"),
            flux_2_pro_1k_usd=Decimal("0.046"),
        )
        qwen = KieGenerationRequest(
            model=KieModelAlias.QWEN2_IMAGE_EDIT,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt="edit",
            references=_references(1),
            aspect_ratio="1:1",
            resolution="2K",
        )
        wan = KieGenerationRequest(
            model=KieModelAlias.WAN_27_IMAGE,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt="edit",
            references=_references(1),
            aspect_ratio="1:1",
            resolution="2K",
        )
        flux = KieGenerationRequest(
            model=KieModelAlias.FLUX_2_PRO_IMAGE,
            input_mode=KieInputMode.PHOTO_TEXT,
            prompt="edit",
            references=_references(1),
            aspect_ratio="auto",
            resolution="1K",
        )
        self.assertEqual(Decimal("0.021"), pricing.estimate_usd(qwen))
        self.assertEqual(Decimal("0.081"), pricing.estimate_usd(wan))
        self.assertEqual(Decimal("0.046"), pricing.estimate_usd(flux))


if __name__ == "__main__":
    unittest.main()

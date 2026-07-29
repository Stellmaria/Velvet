from __future__ import annotations

import os
import unittest
from collections.abc import Mapping
from decimal import Decimal
from unittest.mock import patch

from velvet_bot.core.config.kie import load_kie_settings
from velvet_bot.domains.media_generation import (
    KieContentMode,
    KieInputMode,
    KieModelAlias,
    KieModelCatalog,
    KiePricing,
    KieReferenceImage,
)
from velvet_bot.infrastructure.ai import KieClient
from velvet_bot.presentation.telegram.routers.workspace_meow_video import (
    build_video_source_keyboard,
)
from velvet_bot.presentation.telegram.routers.workspace_meow_video_simple import (
    _build_request,
    _validated_resolution,
    build_video_quality_keyboard,
    build_video_review_keyboard,
)


def _labels(keyboard) -> list[str]:
    return [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]


def _reference() -> KieReferenceImage:
    return KieReferenceImage(
        telegram_file_id="telegram-file",
        telegram_file_unique_id="telegram-unique",
        source="upload",
        mime_type="image/png",
        file_name="portrait.png",
        file_size=1024,
    )


class MeowVideoUIContractTests(unittest.TestCase):
    def test_source_keyboard_offers_database_and_upload(self) -> None:
        self.assertEqual(
            ["Выбрать из базы", "Отправить фото", "Отмена"],
            _labels(build_video_source_keyboard(workspace_id=9)),
        )

    def test_quality_keyboard_exposes_only_resolution_and_edit_actions(self) -> None:
        labels = _labels(
            build_video_quality_keyboard(
                workspace_id=9,
                resolution="480p",
            )
        )
        self.assertEqual(
            [
                "✓ 480p",
                "720p",
                "Изменить фото",
                "Изменить текст",
                "Отмена",
            ],
            labels,
        )
        self.assertNotIn("Normal", labels)
        self.assertNotIn("Fun", labels)
        self.assertNotIn("Spicy", labels)
        self.assertFalse(any("сек" in label for label in labels))
        self.assertFalse(any(":" in label for label in labels))

    def test_review_requires_explicit_launch(self) -> None:
        self.assertEqual(
            ["Запустить видео", "Изменить качество", "Отмена"],
            _labels(build_video_review_keyboard(workspace_id=9)),
        )


class MeowVideoRequestTests(unittest.TestCase):
    def test_domain_request_keeps_filter_override_for_provider_adapter(self) -> None:
        request = _build_request(
            reference=_reference(),
            prompt="Slow dolly-in while hair and curtains move in the wind.",
            resolution="720p",
        ).with_image_urls(("https://files.example/portrait.png",))

        self.assertIs(request.model, KieModelAlias.GROK_IMAGINE_VIDEO)
        self.assertIs(request.input_mode, KieInputMode.PHOTO_TEXT)
        self.assertIs(request.content_mode, KieContentMode.MATURE)
        self.assertEqual(1, len(request.references))
        self.assertEqual(False, request.extra_input["nsfw_checker"])
        self.assertEqual("720p", request.resolution)

    def test_video_price_uses_hidden_minimum_duration_for_budget_guard(self) -> None:
        pricing = KiePricing(
            grok_480p_usd_per_second=Decimal("0.008"),
            grok_720p_usd_per_second=Decimal("0.015"),
        )
        low = _build_request(
            reference=_reference(),
            prompt="motion",
            resolution="480p",
        )
        high = _build_request(
            reference=_reference(),
            prompt="motion",
            resolution="720p",
        )
        self.assertEqual(Decimal("0.048"), pricing.estimate_usd(low))
        self.assertEqual(Decimal("0.090"), pricing.estimate_usd(high))
        self.assertEqual(
            Decimal("9.00"),
            pricing.estimate_rub(high, usd_to_rub=Decimal("100")),
        )

    def test_invalid_resolution_falls_back_to_480p(self) -> None:
        self.assertEqual(
            "480p",
            _validated_resolution({"meow_video_resolution": "8K"}),
        )


class KieGrokClientCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_sends_minimal_uncensored_single_image_payload(self) -> None:
        calls: list[Mapping[str, object]] = []

        def transport(method, url, headers, payload, timeout):
            del method, url, headers, timeout
            if payload is not None:
                calls.append(payload)
            return {"code": 200, "data": {"taskId": "grok-provider-1"}}

        client = KieClient(
            api_key="secret",
            models=KieModelCatalog(
                grok_imagine_video="grok-imagine/image-to-video"
            ),
            transport=transport,
        )
        request = _build_request(
            reference=_reference(),
            prompt="Slow camera orbit.",
            resolution="720p",
        ).with_image_urls(("https://files.example/portrait.png",))

        task_id = await client.create_task(request)

        self.assertEqual("grok-provider-1", task_id)
        self.assertEqual(1, len(calls))
        provider_input = calls[0]["input"]
        self.assertIsInstance(provider_input, Mapping)
        assert isinstance(provider_input, Mapping)
        self.assertEqual(
            {
                "prompt": "Slow camera orbit.",
                "resolution": "720p",
                "image_urls": ["https://files.example/portrait.png"],
                "nsfw_checker": False,
            },
            dict(provider_input),
        )
        self.assertNotIn("duration", provider_input)
        self.assertNotIn("aspect_ratio", provider_input)
        self.assertNotIn("mode", provider_input)


class KieGrokConfigTests(unittest.TestCase):
    def test_new_image_to_video_env_takes_precedence_over_legacy_value(self) -> None:
        with patch.dict(
            os.environ,
            {
                "KIE_ENABLED": "false",
                "KIE_GROK_IMAGINE_VIDEO_MODEL": "grok-imagine/text-to-video",
                "KIE_GROK_IMAGINE_IMAGE_TO_VIDEO_MODEL": (
                    "grok-imagine/image-to-video"
                ),
            },
            clear=False,
        ):
            settings = load_kie_settings()
        self.assertEqual(
            "grok-imagine/image-to-video",
            settings.models.grok_imagine_video,
        )

    def test_image_to_video_is_the_default_when_no_grok_env_is_set(self) -> None:
        with patch.dict(os.environ, {"KIE_ENABLED": "false"}, clear=False):
            with patch.dict(
                os.environ,
                {
                    "KIE_GROK_IMAGINE_VIDEO_MODEL": "",
                    "KIE_GROK_IMAGINE_IMAGE_TO_VIDEO_MODEL": "",
                },
                clear=False,
            ):
                settings = load_kie_settings()
        self.assertEqual(
            "grok-imagine/image-to-video",
            settings.models.grok_imagine_video,
        )


if __name__ == "__main__":
    unittest.main()

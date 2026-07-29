from __future__ import annotations

import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from velvet_bot.core.config.kie import load_kie_settings
from velvet_bot.domains.media_generation import (
    KieContentMode,
    KieInputMode,
    KieModelAlias,
    KiePricing,
    KieReferenceImage,
)
from velvet_bot.presentation.telegram.routers.workspace_meow_video import (
    _build_request,
    _validated_settings,
    build_video_review_keyboard,
    build_video_settings_keyboard,
    build_video_source_keyboard,
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

    def test_settings_keyboard_exposes_safe_grok_v1_options(self) -> None:
        labels = _labels(
            build_video_settings_keyboard(
                workspace_id=9,
                resolution="480p",
                duration=6,
                aspect_ratio="9:16",
                mode="normal",
            )
        )
        self.assertIn("✓ 480p", labels)
        self.assertIn("720p", labels)
        self.assertIn("✓ 6 сек", labels)
        self.assertIn("10 сек", labels)
        self.assertIn("✓ 9:16", labels)
        self.assertIn("16:9", labels)
        self.assertIn("✓ Обычный", labels)
        self.assertIn("Весёлый", labels)
        self.assertNotIn("Spicy", labels)
        self.assertIn("Проверить и запустить", labels)

    def test_review_requires_explicit_launch(self) -> None:
        self.assertEqual(
            ["Запустить видео", "Изменить параметры", "Отмена"],
            _labels(build_video_review_keyboard(workspace_id=9)),
        )


class MeowVideoRequestTests(unittest.TestCase):
    def test_grok_v1_payload_uses_one_image_prompt_and_mature_override(self) -> None:
        request = _build_request(
            reference=_reference(),
            prompt="Slow dolly-in while hair and curtains move in the wind.",
            resolution="720p",
            duration=10,
            aspect_ratio="9:16",
            mode="fun",
        ).with_image_urls(("https://files.example/portrait.png",))

        self.assertIs(request.model, KieModelAlias.GROK_IMAGINE_VIDEO)
        self.assertIs(request.input_mode, KieInputMode.PHOTO_TEXT)
        self.assertIs(request.content_mode, KieContentMode.MATURE)
        self.assertEqual(1, len(request.references))
        self.assertEqual(
            {
                "prompt": "Slow dolly-in while hair and curtains move in the wind.",
                "aspect_ratio": "9:16",
                "resolution": "720p",
                "duration": 10,
                "mode": "fun",
                "image_urls": ["https://files.example/portrait.png"],
                "nsfw_checker": False,
            },
            request.to_input(),
        )

    def test_video_price_is_duration_and_resolution_aware(self) -> None:
        pricing = KiePricing(
            grok_480p_usd_per_second=Decimal("0.008"),
            grok_720p_usd_per_second=Decimal("0.015"),
        )
        low = _build_request(
            reference=_reference(),
            prompt="motion",
            resolution="480p",
            duration=6,
            aspect_ratio="9:16",
            mode="normal",
        )
        high = _build_request(
            reference=_reference(),
            prompt="motion",
            resolution="720p",
            duration=10,
            aspect_ratio="16:9",
            mode="normal",
        )
        self.assertEqual(Decimal("0.048"), pricing.estimate_usd(low))
        self.assertEqual(Decimal("0.150"), pricing.estimate_usd(high))
        self.assertEqual(
            Decimal("15.00"),
            pricing.estimate_rub(high, usd_to_rub=Decimal("100")),
        )

    def test_invalid_state_values_fall_back_to_bounded_defaults(self) -> None:
        self.assertEqual(
            ("480p", 6, "9:16", "normal"),
            _validated_settings(
                {
                    "meow_video_resolution": "8K",
                    "meow_video_duration": 999,
                    "meow_video_aspect_ratio": "4:5",
                    "meow_video_mode": "spicy",
                }
            ),
        )


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

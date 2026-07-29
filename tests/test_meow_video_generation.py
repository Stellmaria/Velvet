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
    build_video_model_keyboard,
    build_video_review_keyboard,
    build_video_settings_keyboard,
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

    def test_model_keyboard_exposes_three_video_engines(self) -> None:
        self.assertEqual(
            [
                "✓ Grok · дёшево",
                "Seedance · баланс",
                "Wan · максимум",
                "Изменить фото",
                "Изменить текст",
                "Отмена",
            ],
            _labels(build_video_model_keyboard(workspace_id=9, model="grok")),
        )

    def test_grok_settings_only_show_480p_and_720p(self) -> None:
        labels = _labels(
            build_video_settings_keyboard(
                workspace_id=9,
                model="grok",
                resolution="480p",
                duration=6,
                generate_audio=False,
            )
        )
        self.assertIn("✓ 480p", labels)
        self.assertIn("720p", labels)
        self.assertNotIn("1080p", labels)
        self.assertFalse(any("сек" in label for label in labels))
        self.assertNotIn("Со звуком", labels)

    def test_seedance_settings_offer_audio_and_three_resolutions(self) -> None:
        labels = _labels(
            build_video_settings_keyboard(
                workspace_id=9,
                model="seedance",
                resolution="720p",
                duration=5,
                generate_audio=True,
            )
        )
        self.assertIn("480p", labels)
        self.assertIn("✓ 720p", labels)
        self.assertIn("1080p", labels)
        self.assertIn("Без звука", labels)
        self.assertIn("✓ Со звуком", labels)
        self.assertFalse(any("сек" in label for label in labels))

    def test_wan_settings_offer_resolution_and_duration(self) -> None:
        labels = _labels(
            build_video_settings_keyboard(
                workspace_id=9,
                model="wan",
                resolution="1080p",
                duration=10,
                generate_audio=False,
            )
        )
        self.assertIn("720p", labels)
        self.assertIn("✓ 1080p", labels)
        self.assertIn("5 сек", labels)
        self.assertIn("✓ 10 сек", labels)
        self.assertIn("15 сек", labels)
        self.assertNotIn("Со звуком", labels)

    def test_review_requires_explicit_launch(self) -> None:
        self.assertEqual(
            [
                "Запустить видео",
                "Изменить параметры",
                "Изменить модель",
                "Отмена",
            ],
            _labels(build_video_review_keyboard(workspace_id=9)),
        )


class MeowVideoRequestTests(unittest.TestCase):
    def test_grok_request_keeps_uncensored_override(self) -> None:
        request = _build_request(
            reference=_reference(),
            prompt="Slow dolly-in.",
            model="grok",
            resolution="720p",
        ).with_image_urls(("https://files.example/portrait.png",))
        self.assertIs(request.model, KieModelAlias.GROK_IMAGINE_VIDEO)
        self.assertIs(request.input_mode, KieInputMode.PHOTO_TEXT)
        self.assertIs(request.content_mode, KieContentMode.MATURE)
        self.assertEqual(False, request.extra_input["nsfw_checker"])

    def test_seedance_request_keeps_audio_and_uncensored_override(self) -> None:
        request = _build_request(
            reference=_reference(),
            prompt="Camera circles the subject.",
            model="seedance",
            resolution="1080p",
            duration=5,
            generate_audio=True,
        ).with_image_urls(("https://files.example/portrait.png",))
        self.assertIs(request.model, KieModelAlias.SEEDANCE_15_PRO_VIDEO)
        self.assertEqual(True, request.extra_input["generate_audio"])
        self.assertEqual(False, request.extra_input["nsfw_checker"])
        self.assertEqual(5, request.duration_seconds)

    def test_wan_request_keeps_selected_duration(self) -> None:
        request = _build_request(
            reference=_reference(),
            prompt="Natural body motion and a slow push-in.",
            model="wan",
            resolution="1080p",
            duration=15,
        ).with_image_urls(("https://files.example/portrait.png",))
        self.assertIs(request.model, KieModelAlias.WAN_26_IMAGE_TO_VIDEO)
        self.assertEqual(15, request.duration_seconds)
        self.assertEqual(False, request.extra_input["nsfw_checker"])

    def test_pricing_distinguishes_audio_and_models(self) -> None:
        pricing = KiePricing(
            seedance_720p_no_audio_usd_per_second=Decimal("0.0175"),
            seedance_720p_audio_usd_per_second=Decimal("0.035"),
            wan_720p_usd_per_second=Decimal("0.07"),
        )
        seedance_silent = _build_request(
            reference=_reference(),
            prompt="motion",
            model="seedance",
            resolution="720p",
            duration=5,
            generate_audio=False,
        )
        seedance_audio = _build_request(
            reference=_reference(),
            prompt="motion",
            model="seedance",
            resolution="720p",
            duration=5,
            generate_audio=True,
        )
        wan = _build_request(
            reference=_reference(),
            prompt="motion",
            model="wan",
            resolution="720p",
            duration=5,
        )
        self.assertEqual(Decimal("0.0875"), pricing.estimate_usd(seedance_silent))
        self.assertEqual(Decimal("0.175"), pricing.estimate_usd(seedance_audio))
        self.assertEqual(Decimal("0.35"), pricing.estimate_usd(wan))
        self.assertEqual(
            Decimal("35.00"),
            pricing.estimate_rub(wan, usd_to_rub=Decimal("100")),
        )

    def test_invalid_resolution_uses_model_default(self) -> None:
        self.assertEqual(
            "480p",
            _validated_resolution(
                {"meow_video_resolution": "8K"},
                model="grok",
            ),
        )
        self.assertEqual(
            "720p",
            _validated_resolution(
                {"meow_video_resolution": "8K"},
                model="wan",
            ),
        )


class KieVideoClientCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    def _client_and_calls(self, models: KieModelCatalog):
        calls: list[Mapping[str, object]] = []

        def transport(method, url, headers, payload, timeout):
            del method, url, headers, timeout
            if payload is not None:
                calls.append(payload)
            return {"code": 200, "data": {"taskId": "provider-task-1"}}

        return KieClient(api_key="secret", models=models, transport=transport), calls

    async def test_grok_adapter_sends_minimal_payload(self) -> None:
        client, calls = self._client_and_calls(
            KieModelCatalog(grok_imagine_video="grok-imagine/image-to-video")
        )
        request = _build_request(
            reference=_reference(),
            prompt="Slow camera orbit.",
            model="grok",
            resolution="720p",
        ).with_image_urls(("https://files.example/portrait.png",))
        await client.create_task(request)
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

    async def test_seedance_adapter_uses_input_urls_and_audio(self) -> None:
        client, calls = self._client_and_calls(
            KieModelCatalog(seedance_15_pro_video="bytedance/seedance-1.5-pro")
        )
        request = _build_request(
            reference=_reference(),
            prompt="Natural movement with ambient sound.",
            model="seedance",
            resolution="720p",
            duration=5,
            generate_audio=True,
        ).with_image_urls(("https://files.example/portrait.png",))
        await client.create_task(request)
        provider_input = calls[0]["input"]
        self.assertIsInstance(provider_input, Mapping)
        assert isinstance(provider_input, Mapping)
        self.assertEqual(
            {
                "prompt": "Natural movement with ambient sound.",
                "input_urls": ["https://files.example/portrait.png"],
                "aspect_ratio": "1:1",
                "resolution": "720p",
                "duration": 5,
                "fixed_lens": False,
                "generate_audio": True,
                "nsfw_checker": False,
            },
            dict(provider_input),
        )

    async def test_wan_adapter_uses_string_duration(self) -> None:
        client, calls = self._client_and_calls(
            KieModelCatalog(wan_26_image_to_video="wan/2-6-image-to-video")
        )
        request = _build_request(
            reference=_reference(),
            prompt="Slow cinematic push-in.",
            model="wan",
            resolution="1080p",
            duration=10,
        ).with_image_urls(("https://files.example/portrait.png",))
        await client.create_task(request)
        provider_input = calls[0]["input"]
        self.assertIsInstance(provider_input, Mapping)
        assert isinstance(provider_input, Mapping)
        self.assertEqual(
            {
                "prompt": "Slow cinematic push-in.",
                "image_urls": ["https://files.example/portrait.png"],
                "duration": "10",
                "resolution": "1080p",
                "nsfw_checker": False,
            },
            dict(provider_input),
        )


class KieVideoConfigTests(unittest.TestCase):
    def test_video_model_defaults_are_image_to_video_routes(self) -> None:
        with patch.dict(
            os.environ,
            {
                "KIE_ENABLED": "false",
                "KIE_GROK_IMAGINE_VIDEO_MODEL": "",
                "KIE_GROK_IMAGINE_IMAGE_TO_VIDEO_MODEL": "",
                "KIE_SEEDANCE_15_PRO_MODEL": "",
                "KIE_WAN_26_IMAGE_TO_VIDEO_MODEL": "",
            },
            clear=False,
        ):
            settings = load_kie_settings()
        self.assertEqual(
            "grok-imagine/image-to-video",
            settings.models.grok_imagine_video,
        )
        self.assertEqual(
            "bytedance/seedance-1.5-pro",
            settings.models.seedance_15_pro_video,
        )
        self.assertEqual(
            "wan/2-6-image-to-video",
            settings.models.wan_26_image_to_video,
        )

    def test_explicit_video_env_values_are_loaded(self) -> None:
        with patch.dict(
            os.environ,
            {
                "KIE_ENABLED": "false",
                "KIE_SEEDANCE_15_PRO_MODEL": "custom/seedance",
                "KIE_WAN_26_IMAGE_TO_VIDEO_MODEL": "custom/wan",
                "KIE_SEEDANCE_15_720P_AUDIO_USD_PER_SECOND": "0.123",
                "KIE_WAN_26_1080P_USD_PER_SECOND": "0.456",
            },
            clear=False,
        ):
            settings = load_kie_settings()
        self.assertEqual("custom/seedance", settings.models.seedance_15_pro_video)
        self.assertEqual("custom/wan", settings.models.wan_26_image_to_video)
        self.assertEqual(
            Decimal("0.123"),
            settings.pricing.seedance_720p_audio_usd_per_second,
        )
        self.assertEqual(
            Decimal("0.456"),
            settings.pricing.wan_1080p_usd_per_second,
        )


if __name__ == "__main__":
    unittest.main()

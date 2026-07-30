from __future__ import annotations

import os
import unittest
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from velvet_bot.core.config.kie import load_kie_settings
from velvet_bot.domains.media_generation import (
    KieModelAlias,
    KieModelCatalog,
    KiePricing,
    KieReferenceImage,
)
from velvet_bot.infrastructure.ai import KieClient
from velvet_bot.presentation.telegram.routers.workspace_auf_video import (
    build_video_source_keyboard,
)
from velvet_bot.presentation.telegram.routers.workspace_auf_video_simple import (
    _build_request,
    _parse_duration,
    _settings_text,
    _validated_resolution,
    build_video_model_keyboard,
    build_video_review_keyboard,
    build_video_settings_keyboard,
    build_video_template_keyboard,
)


def _labels(keyboard) -> list[str]:
    return [button.text for row in keyboard.inline_keyboard for button in row]


def _reference(name: str = "portrait.png") -> KieReferenceImage:
    return KieReferenceImage(
        telegram_file_id=f"telegram-{name}",
        telegram_file_unique_id=f"unique-{name}",
        source="upload",
        mime_type="image/png",
        file_name=name,
        file_size=1024,
    )


class MeowVideoUIContractTests(unittest.TestCase):
    def test_source_keyboard_offers_database_and_upload(self) -> None:
        self.assertEqual(
            ["Выбрать из базы", "Отправить фото", "Отмена"],
            _labels(build_video_source_keyboard(workspace_id=9)),
        )

    def test_model_keyboard_exposes_wan_27(self) -> None:
        labels = _labels(build_video_model_keyboard(workspace_id=9, model="wan"))
        self.assertIn("✓ Wan 2.7", labels)
        self.assertIn("Grok v1 · дёшево", labels)
        self.assertIn("Grok 1.5 · качество", labels)
        self.assertIn("Seedance 1.5 Pro", labels)
        self.assertNotIn("Wan 2.6", labels)

    def test_seedance_settings_only_expose_requested_controls(self) -> None:
        labels = _labels(
            build_video_settings_keyboard(
                workspace_id=9,
                model="seedance",
                resolution="720p",
                duration=8,
                generate_audio=True,
            )
        )
        self.assertIn("480p", labels)
        self.assertIn("✓ 720p", labels)
        self.assertIn("1080p", labels)
        self.assertIn("Без звука", labels)
        self.assertIn("✓ Со звуком", labels)
        self.assertIn("Длительность · 8 сек", labels)
        self.assertIn("Стандартный шаблон", labels)
        self.assertFalse(any("Fixed" in label for label in labels))
        self.assertFalse(any("NSFW" in label for label in labels))

    def test_wan_settings_use_frame_mode_and_free_duration_input(self) -> None:
        labels = _labels(
            build_video_settings_keyboard(
                workspace_id=9,
                model="wan",
                resolution="1080p",
                duration=11,
                generate_audio=False,
                wan_mode="first_last",
                has_last_frame=False,
            )
        )
        self.assertIn("720p", labels)
        self.assertIn("✓ 1080p", labels)
        self.assertIn("Первый кадр", labels)
        self.assertIn("✓ Первый + последний", labels)
        self.assertIn("Длительность · 11 сек", labels)
        self.assertIn("Добавить последний кадр", labels)
        self.assertNotIn("5 сек", labels)
        self.assertNotIn("10 сек", labels)
        self.assertNotIn("15 сек", labels)
        self.assertFalse(any("Watermark" in label for label in labels))
        self.assertFalse(any("Seed" in label for label in labels))

    def test_template_keyboard_can_save_and_apply(self) -> None:
        self.assertEqual(
            ["Сохранить текущие стандартом", "Применить стандартный", "К параметрам"],
            _labels(build_video_template_keyboard(workspace_id=9, has_template=True)),
        )

    def test_settings_show_current_and_comparative_cost(self) -> None:
        text = _settings_text(
            model="wan",
            resolution="1080p",
            duration=10,
            generate_audio=False,
            wan_mode="first",
            estimated_usd=Decimal("1.20"),
            estimated_rub=Decimal("120.00"),
            cost_change={
                "old_usd": "0.40",
                "old_rub": "40.00",
                "new_usd": "1.20",
                "new_rub": "120.00",
                "reason": "разрешение 720p → 1080p",
            },
        )
        self.assertIn("Текущая расчётная стоимость", text)
        self.assertIn("Предварительный анализ стоимости", text)
        self.assertIn("Было:", text)
        self.assertIn("Стало:", text)
        self.assertIn("Разница:", text)
        self.assertIn("Причина:", text)

    def test_duration_parser_accepts_arbitrary_supported_integer(self) -> None:
        self.assertEqual(8, _parse_duration("8"))
        self.assertEqual(12, _parse_duration("12 сек"))
        self.assertIsNone(_parse_duration("1"))
        self.assertIsNone(_parse_duration("16"))
        self.assertIsNone(_parse_duration("пять"))

    def test_review_requires_explicit_launch(self) -> None:
        self.assertEqual(
            ["Запустить видео", "Изменить параметры", "Изменить модель", "Отмена"],
            _labels(build_video_review_keyboard(workspace_id=9)),
        )


class MeowVideoRequestTests(unittest.TestCase):
    def test_grok_15_request_uses_separate_contract_without_legacy_mode(self) -> None:
        request = _build_request(
            reference=_reference(),
            prompt="Natural cinematic movement.",
            model="grok15",
            resolution="720p",
            duration=8,
        ).with_image_urls(("https://files.example/portrait.png",))
        self.assertIs(request.model, KieModelAlias.GROK_IMAGINE_VIDEO_15)
        payload = request.to_input()
        self.assertEqual(["https://files.example/portrait.png"], payload["image_urls"])
        self.assertEqual(8, payload["duration"])
        self.assertEqual("auto", payload["aspect_ratio"])
        self.assertIs(False, payload["nsfw_checker"])
        self.assertNotIn("mode", payload)

    def test_seedance_request_keeps_hidden_provider_controls(self) -> None:
        request = _build_request(
            reference=_reference(),
            prompt="Camera circles the subject.",
            model="seedance",
            resolution="1080p",
            duration=8,
            generate_audio=True,
        ).with_image_urls(("https://files.example/portrait.png",))
        self.assertIs(request.model, KieModelAlias.SEEDANCE_15_PRO_VIDEO)
        self.assertEqual(True, request.extra_input["generate_audio"])
        self.assertEqual(False, request.extra_input["fixed_lens"])
        self.assertEqual(False, request.extra_input["nsfw_checker"])
        self.assertEqual(8, request.duration_seconds)

    def test_wan_request_keeps_two_frame_mode_and_hidden_overrides(self) -> None:
        request = _build_request(
            reference=_reference("first.png"),
            last_reference=_reference("last.png"),
            prompt="Natural body motion and a slow push-in.",
            model="wan",
            resolution="1080p",
            duration=12,
            wan_mode="first_last",
        ).with_image_urls(
            ("https://files.example/first.png", "https://files.example/last.png")
        )
        self.assertIs(request.model, KieModelAlias.WAN_26_IMAGE_TO_VIDEO)
        self.assertEqual(12, request.duration_seconds)
        self.assertEqual("first_last", request.extra_input["wan_mode"])
        self.assertEqual(True, request.extra_input["prompt_extend"])
        self.assertEqual(False, request.extra_input["watermark"])
        self.assertEqual(False, request.extra_input["nsfw_checker"])

    def test_pricing_distinguishes_audio_resolution_and_duration(self) -> None:
        pricing = KiePricing(
            seedance_720p_no_audio_usd_per_second=Decimal("0.0175"),
            seedance_720p_audio_usd_per_second=Decimal("0.035"),
            wan_720p_usd_per_second=Decimal("0.08"),
            wan_1080p_usd_per_second=Decimal("0.12"),
        )
        seedance_silent = _build_request(
            reference=_reference(), prompt="motion", model="seedance",
            resolution="720p", duration=8, generate_audio=False,
        )
        seedance_audio = _build_request(
            reference=_reference(), prompt="motion", model="seedance",
            resolution="720p", duration=8, generate_audio=True,
        )
        wan_720 = _build_request(
            reference=_reference(), prompt="motion", model="wan",
            resolution="720p", duration=8,
        )
        wan_1080 = _build_request(
            reference=_reference(), prompt="motion", model="wan",
            resolution="1080p", duration=8,
        )
        self.assertEqual(Decimal("0.1400"), pricing.estimate_usd(seedance_silent))
        self.assertEqual(Decimal("0.280"), pricing.estimate_usd(seedance_audio))
        self.assertEqual(Decimal("0.64"), pricing.estimate_usd(wan_720))
        self.assertEqual(Decimal("0.96"), pricing.estimate_usd(wan_1080))

    def test_invalid_resolution_uses_model_default(self) -> None:
        self.assertEqual(
            "480p",
            _validated_resolution({"auf_video_resolution": "8K"}, model="grok"),
        )
        self.assertEqual(
            "720p",
            _validated_resolution({"auf_video_resolution": "8K"}, model="wan"),
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

    async def test_grok_15_adapter_uses_preview_model_and_new_payload(self) -> None:
        client, calls = self._client_and_calls(
            KieModelCatalog(grok_imagine_video_15="grok-imagine-video-1-5-preview")
        )
        request = _build_request(
            reference=_reference(), prompt="Slow camera move.", model="grok15",
            resolution="480p", duration=9,
        ).with_image_urls(("https://files.example/portrait.png",))
        await client.create_task(request)
        self.assertEqual("grok-imagine-video-1-5-preview", calls[0]["model"])
        provider_input = calls[0]["input"]
        assert isinstance(provider_input, Mapping)
        self.assertEqual(9, provider_input["duration"])
        self.assertNotIn("mode", provider_input)

    async def test_seedance_adapter_uses_numeric_duration_and_audio(self) -> None:
        client, calls = self._client_and_calls(
            KieModelCatalog(seedance_15_pro_video="bytedance/seedance-1.5-pro")
        )
        request = _build_request(
            reference=_reference(),
            prompt="Natural movement with ambient sound.",
            model="seedance",
            resolution="720p",
            duration=8,
            generate_audio=True,
        ).with_image_urls(("https://files.example/portrait.png",))
        await client.create_task(request)
        provider_input = calls[0]["input"]
        self.assertIsInstance(provider_input, Mapping)
        assert isinstance(provider_input, Mapping)
        self.assertEqual(8, provider_input["duration"])
        self.assertEqual(True, provider_input["generate_audio"])
        self.assertEqual(False, provider_input["fixed_lens"])
        self.assertEqual(False, provider_input["nsfw_checker"])

    async def test_wan_27_adapter_uses_first_and_last_frame_urls(self) -> None:
        client, calls = self._client_and_calls(
            KieModelCatalog(wan_26_image_to_video="wan/2-7-image-to-video")
        )
        request = _build_request(
            reference=_reference("first.png"),
            last_reference=_reference("last.png"),
            prompt="Slow cinematic push-in.",
            model="wan",
            resolution="1080p",
            duration=10,
            wan_mode="first_last",
        ).with_image_urls(
            ("https://files.example/first.png", "https://files.example/last.png")
        )
        await client.create_task(request)
        self.assertEqual("wan/2-7-image-to-video", calls[0]["model"])
        provider_input = calls[0]["input"]
        self.assertIsInstance(provider_input, Mapping)
        assert isinstance(provider_input, Mapping)
        self.assertEqual(
            {
                "prompt": "Slow cinematic push-in.",
                "first_frame_url": "https://files.example/first.png",
                "last_frame_url": "https://files.example/last.png",
                "resolution": "1080p",
                "duration": 10,
                "prompt_extend": True,
                "watermark": False,
                "nsfw_checker": False,
            },
            dict(provider_input),
        )

    async def test_wan_27_adapter_omits_last_frame_in_first_only_mode(self) -> None:
        client, calls = self._client_and_calls(
            KieModelCatalog(wan_26_image_to_video="wan/2-7-image-to-video")
        )
        request = _build_request(
            reference=_reference(), prompt="Subtle movement.", model="wan",
            resolution="720p", duration=7, wan_mode="first",
        ).with_image_urls(("https://files.example/portrait.png",))
        await client.create_task(request)
        provider_input = calls[0]["input"]
        assert isinstance(provider_input, Mapping)
        self.assertNotIn("last_frame_url", provider_input)
        self.assertEqual(7, provider_input["duration"])


class KieVideoConfigTests(unittest.TestCase):
    def test_video_model_defaults_use_wan_27(self) -> None:
        with patch.dict(
            os.environ,
            {
                "KIE_ENABLED": "false",
                "KIE_GROK_IMAGINE_VIDEO_MODEL": "",
                "KIE_GROK_IMAGINE_IMAGE_TO_VIDEO_MODEL": "",
                "KIE_SEEDANCE_15_PRO_MODEL": "",
                "KIE_WAN_27_IMAGE_TO_VIDEO_MODEL": "",
                "KIE_WAN_26_IMAGE_TO_VIDEO_MODEL": "",
                "KIE_WAN_27_720P_USD_PER_SECOND": "",
                "KIE_WAN_26_720P_USD_PER_SECOND": "",
                "KIE_WAN_27_1080P_USD_PER_SECOND": "",
                "KIE_WAN_26_1080P_USD_PER_SECOND": "",
            },
            clear=False,
        ):
            settings = load_kie_settings()
        self.assertEqual("grok-imagine-video-1-5-preview", settings.models.grok_imagine_video_15)
        self.assertEqual("wan/2-7-image-to-video", settings.models.wan_26_image_to_video)
        self.assertEqual(Decimal("0.08"), settings.pricing.wan_720p_usd_per_second)
        self.assertEqual(Decimal("0.12"), settings.pricing.wan_1080p_usd_per_second)

    def test_new_wan_env_values_take_priority_over_legacy(self) -> None:
        with patch.dict(
            os.environ,
            {
                "KIE_ENABLED": "false",
                "KIE_WAN_27_IMAGE_TO_VIDEO_MODEL": "custom/wan-27",
                "KIE_WAN_26_IMAGE_TO_VIDEO_MODEL": "legacy/wan-26",
                "KIE_WAN_27_1080P_USD_PER_SECOND": "0.456",
                "KIE_WAN_26_1080P_USD_PER_SECOND": "0.999",
            },
            clear=False,
        ):
            settings = load_kie_settings()
        self.assertEqual("custom/wan-27", settings.models.wan_26_image_to_video)
        self.assertEqual(Decimal("0.456"), settings.pricing.wan_1080p_usd_per_second)

    def test_template_migration_has_one_standard_per_workspace_and_model(self) -> None:
        migration = Path("migrations/917_auf_video_templates.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_video_templates", migration)
        self.assertIn("PRIMARY KEY (workspace_id, model)", migration)
        self.assertIn("duration_seconds BETWEEN 2 AND 15", migration)


if __name__ == "__main__":
    unittest.main()

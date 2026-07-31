from __future__ import annotations

import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from velvet_bot.core.config.settings import load_settings
from velvet_bot.domains.vision_routing.factory import _route_config
from velvet_bot.domains.vision_routing.models import VisionRoute


_BASE_ENV = {
    "BOT_TOKEN": "telegram-token",
    "DATABASE_URL": "postgresql://velvet:test@localhost:5432/velvet",
    "ALLOWED_USER_IDS": "100",
    "AI_VISION_ENABLED": "true",
    "AI_VISION_PROVIDER": "local_openai_compatible",
    "AI_VISION_BASE_URL": "http://vision-gateway:8080/v1",
    "AI_VISION_MODEL": "qwen3-vl:8b-instruct-q4_K_M",
}


class LocalVisionProviderContractTests(unittest.TestCase):
    def _load(self, **values: str):
        environment = {**_BASE_ENV, **values}
        with patch.dict(os.environ, environment, clear=True), patch(
            "velvet_bot.core.config.settings.load_dotenv"
        ):
            return load_settings()

    def test_internal_provider_does_not_require_api_key(self) -> None:
        settings = self._load()
        self.assertEqual(settings.ai_vision_provider, "local_openai_compatible")
        self.assertEqual(
            settings.ai_vision_base_url,
            "http://vision-gateway:8080/v1",
        )
        self.assertIsNone(settings.ai_vision_api_key)

    def test_internal_provider_rejects_public_and_loopback_hosts(self) -> None:
        for base_url in (
            "https://example.com/v1",
            "http://127.0.0.1:8080/v1",
            "http://localhost:8080/v1",
        ):
            with self.subTest(base_url=base_url), self.assertRaisesRegex(
                RuntimeError,
                "Compose host",
            ):
                self._load(AI_VISION_BASE_URL=base_url)

    def test_internal_route_has_zero_monetary_pricing(self) -> None:
        with patch.dict(os.environ, _BASE_ENV, clear=True), patch(
            "velvet_bot.core.config.settings.load_dotenv"
        ):
            settings = load_settings()
            route = _route_config(
                settings=settings,
                route=VisionRoute.FLASH,
                default_model=settings.ai_vision_model,
            )

        self.assertFalse(route.pricing.configured)
        self.assertEqual(
            route.pricing.cost(input_tokens=4_000, output_tokens=1_200),
            Decimal("0"),
        )
        self.assertIsNone(route.api_key)

    def test_internal_provider_rejects_credentials_in_url(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "credentials"):
            self._load(
                AI_VISION_BASE_URL="http://user:pass@vision-gateway:8080/v1"
            )


if __name__ == "__main__":
    unittest.main()

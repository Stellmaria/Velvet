from __future__ import annotations

import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from velvet_bot.domains.ai_usage import AITokenPricing
from velvet_bot.domains.vision_routing.factory import (
    _env_flag,
    _validate_sensitive_provider,
)
from velvet_bot.domains.vision_routing.models import VisionRoute, VisionRouteConfig


def _config(provider: str) -> VisionRouteConfig:
    return VisionRouteConfig(
        route=VisionRoute.SENSITIVE,
        provider=provider,
        base_url=(
            "http://vision-gateway:8080/v1"
            if provider == "local_openai_compatible"
            else "https://example.invalid/v1"
        ),
        model="sensitive-model",
        api_key="test-key" if provider == "openai_compatible" else None,
        timeout_seconds=30,
        max_attempts=1,
        pricing=AITokenPricing(
            input_rub_per_million=Decimal("1"),
            output_rub_per_million=Decimal("1"),
        ),
    )


class VisionSensitiveFactoryTests(unittest.TestCase):
    def test_local_sensitive_provider_is_allowed_without_cloud_flag(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            _validate_sensitive_provider(_config("local_openai_compatible"))

    def test_cloud_sensitive_provider_is_rejected_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "cloud sensitive VL запрещён"):
                _validate_sensitive_provider(_config("openai_compatible"))

    def test_cloud_sensitive_provider_stays_rejected_with_legacy_flag(self) -> None:
        with patch.dict(
            os.environ,
            {"AI_VISION_ALLOW_CLOUD_SENSITIVE": "true"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "cloud sensitive VL запрещён"):
                _validate_sensitive_provider(_config("openai_compatible"))

    def test_invalid_cloud_sensitive_flag_fails_closed(self) -> None:
        with patch.dict(
            os.environ,
            {"AI_VISION_ALLOW_CLOUD_SENSITIVE": "perhaps"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "должен быть true/false"):
                _env_flag("AI_VISION_ALLOW_CLOUD_SENSITIVE", default=False)


if __name__ == "__main__":
    unittest.main()

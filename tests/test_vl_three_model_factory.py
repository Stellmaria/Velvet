from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from velvet_bot.domains.vision_routing.factory import build_vision_cascade_router
from velvet_bot.domains.vision_routing.models import VisionAnalysisMode


_SETTINGS = SimpleNamespace(
    ai_vision_model="main-vl",
    ai_vision_compare_model=None,
    ai_vision_provider="local_openai_compatible",
    ai_vision_base_url="http://vision-gateway:8080/v1",
    ai_vision_api_key=None,
    ai_vision_timeout_seconds=300,
    ai_vision_max_attempts=3,
)


class VLThreeModelFactoryTests(unittest.TestCase):
    @staticmethod
    def _build(**environment: str):
        values = {
            "AI_VISION_CLOUD_PRO_ENABLED": "false",
            "AI_VISION_LOCAL_UNCENSORED_ENABLED": "false",
            **environment,
        }
        with patch.dict(os.environ, values, clear=True):
            return build_vision_cascade_router(
                settings=_SETTINGS,  # type: ignore[arg-type]
                database=SimpleNamespace(),  # type: ignore[arg-type]
                ai_usage_service=SimpleNamespace(),  # type: ignore[arg-type]
            )

    def test_optional_routes_are_absent_by_default(self) -> None:
        router = self._build()

        self.assertIsNone(router._pro)  # type: ignore[attr-defined]
        self.assertIsNone(router._sensitive)  # type: ignore[attr-defined]
        self.assertIsNotNone(router._main_sensitive)  # type: ignore[attr-defined]
        self.assertEqual(router._flash.model, router._main_sensitive.model)  # type: ignore[attr-defined]
        self.assertEqual(  # type: ignore[attr-defined]
            VisionAnalysisMode.SENSITIVE,
            router._main_sensitive.mode,
        )

    def test_cloud_pro_enable_requires_cloud_provider_and_pricing(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "цен"):
            self._build(
                AI_VISION_CLOUD_PRO_ENABLED="true",
                AI_VISION_PRO_PROVIDER="openai_compatible",
                AI_VISION_PRO_BASE_URL="https://vision.example/v1",
                AI_VISION_PRO_MODEL="pro-vl",
                AI_VISION_PRO_API_KEY="test-key",
            )

    def test_cloud_pro_can_be_constructed_only_after_explicit_enable(self) -> None:
        router = self._build(
            AI_VISION_CLOUD_PRO_ENABLED="true",
            AI_VISION_PRO_PROVIDER="openai_compatible",
            AI_VISION_PRO_BASE_URL="https://vision.example/v1",
            AI_VISION_PRO_MODEL="pro-vl",
            AI_VISION_PRO_API_KEY="test-key",
            AI_VISION_PRO_INPUT_RUB_PER_1M="10",
            AI_VISION_PRO_OUTPUT_RUB_PER_1M="20",
        )

        self.assertIsNotNone(router._pro)  # type: ignore[attr-defined]
        self.assertEqual("pro-vl", router._pro.model)  # type: ignore[attr-defined]
        self.assertEqual("openai_compatible", router._pro.provider)  # type: ignore[attr-defined]

    def test_uncensored_requires_distinct_model(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "отдельной моделью"):
            self._build(
                AI_VISION_LOCAL_UNCENSORED_ENABLED="true",
                AI_VISION_SENSITIVE_MODEL="main-vl",
            )

    def test_uncensored_can_be_constructed_only_as_local_route(self) -> None:
        router = self._build(
            AI_VISION_LOCAL_UNCENSORED_ENABLED="true",
            AI_VISION_SENSITIVE_PROVIDER="local_openai_compatible",
            AI_VISION_SENSITIVE_BASE_URL="http://vision-gateway:8080/v1",
            AI_VISION_SENSITIVE_MODEL="uncensored-vl",
        )

        self.assertIsNotNone(router._sensitive)  # type: ignore[attr-defined]
        self.assertEqual("uncensored-vl", router._sensitive.model)  # type: ignore[attr-defined]
        # VisionClient normalizes local_openai_compatible to the shared
        # OpenAI-compatible transport internally. Locality is enforced by the
        # factory before construction and by the gateway-only base URL here.
        self.assertEqual("openai_compatible", router._sensitive.provider)  # type: ignore[attr-defined]
        self.assertEqual(  # type: ignore[attr-defined]
            "http://vision-gateway:8080/v1",
            router._sensitive.base_url,
        )

    def test_cloud_sensitive_stays_forbidden_even_with_legacy_flag(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "локальным"):
            self._build(
                AI_VISION_LOCAL_UNCENSORED_ENABLED="true",
                AI_VISION_ALLOW_CLOUD_SENSITIVE="true",
                AI_VISION_SENSITIVE_PROVIDER="openai_compatible",
                AI_VISION_SENSITIVE_BASE_URL="https://vision.example/v1",
                AI_VISION_SENSITIVE_MODEL="uncensored-vl",
                AI_VISION_SENSITIVE_API_KEY="test-key",
                AI_VISION_SENSITIVE_INPUT_RUB_PER_1M="10",
                AI_VISION_SENSITIVE_OUTPUT_RUB_PER_1M="20",
            )


if __name__ == "__main__":
    unittest.main()

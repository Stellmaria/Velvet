from __future__ import annotations

import io
import unittest
from decimal import Decimal
from typing import Any, Mapping

from PIL import Image

from velvet_bot.ai_vision import VisionAnalysisError
from velvet_bot.domains.vision_routing.models import (
    CachedVisionAnalysis,
    VisionProviderAnalysis,
    VisionRoute,
)
from velvet_bot.domains.vision_routing.service import VisionCascadeRouter


def _image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 24), (120, 80, 40)).save(output, format="JPEG")
    return output.getvalue()


def _profile(confidence: int, *, title: str = "Тест") -> dict[str, object]:
    return {
        "series_title_ru": title,
        "summary_ru": "Тестовый профиль.",
        "themes": ["western"],
        "genres": [],
        "settings": ["desert"],
        "eras": [],
        "environment": [],
        "objects": [],
        "wardrobe": [],
        "composition": [],
        "lighting": [],
        "palette": [],
        "mood": [],
        "actions": [],
        "series_keywords": ["western"],
        "people_count": 1,
        "confidence": confidence,
    }


class _FakeClient:
    def __init__(
        self,
        route: VisionRoute,
        *,
        confidence: int = 90,
        error: BaseException | None = None,
    ) -> None:
        self.route = route
        self.provider = "test-provider"
        self.model = f"{route.value}-model"
        self.base_url = "https://example.invalid/v1"
        self.confidence = confidence
        self.error = error
        self.calls = 0
        self.metadata: list[Mapping[str, object]] = []

    async def health(self) -> bool:
        return True

    async def analyze_prepared(
        self,
        prepared: bytes,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
        operation: str,
        metadata: Mapping[str, object],
    ) -> VisionProviderAnalysis:
        self.calls += 1
        self.metadata.append(metadata)
        if self.error is not None:
            raise self.error
        if not prepared.startswith(b"\xff\xd8"):
            raise AssertionError("Expected prepared JPEG")
        return VisionProviderAnalysis(
            profile=_profile(self.confidence, title=self.route.value),
            provider=self.provider,
            model=self.model,
            route=self.route,
            input_tokens=100,
            output_tokens=50,
            usage_reported=True,
            actual_cost_rub=Decimal("0.25"),
        )


class _FakeCache:
    def __init__(self, cached: CachedVisionAnalysis | None = None) -> None:
        self.cached = cached
        self.find_calls: list[dict[str, object]] = []
        self.stored: list[tuple[object, dict[str, Any]]] = []

    async def find(self, **kwargs: object) -> CachedVisionAnalysis | None:
        self.find_calls.append(dict(kwargs))
        return self.cached

    async def store(self, result: object, **kwargs: Any) -> None:
        self.stored.append((result, kwargs))


class VisionCascadeRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_high_confidence_flash_does_not_call_pro(self) -> None:
        flash = _FakeClient(VisionRoute.FLASH, confidence=88)
        pro = _FakeClient(VisionRoute.PRO, confidence=96)
        cache = _FakeCache()
        router = VisionCascadeRouter(
            flash=flash,  # type: ignore[arg-type]
            pro=pro,  # type: ignore[arg-type]
            repository=cache,  # type: ignore[arg-type]
            confidence_threshold=70,
        )

        result = await router.analyze(_image_bytes())

        self.assertEqual(VisionRoute.FLASH, result.route)
        self.assertEqual((VisionRoute.FLASH,), result.attempts)
        self.assertEqual(1, flash.calls)
        self.assertEqual(0, pro.calls)
        self.assertEqual(1, len(cache.stored))
        self.assertEqual("standard", result.metadata["analysis_mode"])

    async def test_low_confidence_flash_calls_pro(self) -> None:
        flash = _FakeClient(VisionRoute.FLASH, confidence=42)
        pro = _FakeClient(VisionRoute.PRO, confidence=91)
        router = VisionCascadeRouter(
            flash=flash,  # type: ignore[arg-type]
            pro=pro,  # type: ignore[arg-type]
            repository=_FakeCache(),  # type: ignore[arg-type]
            confidence_threshold=70,
        )

        result = await router.analyze(_image_bytes())

        self.assertEqual(VisionRoute.PRO, result.route)
        self.assertEqual((VisionRoute.FLASH, VisionRoute.PRO), result.attempts)
        self.assertEqual("low_confidence", result.metadata["fallback_reason"])

    async def test_flash_refusal_uses_pro_not_sensitive(self) -> None:
        flash = _FakeClient(
            VisionRoute.FLASH,
            error=VisionAnalysisError("provider refusal: blocked by content policy"),
        )
        pro = _FakeClient(VisionRoute.PRO, confidence=84)
        sensitive = _FakeClient(VisionRoute.SENSITIVE, confidence=99)
        router = VisionCascadeRouter(
            flash=flash,  # type: ignore[arg-type]
            pro=pro,  # type: ignore[arg-type]
            sensitive=sensitive,  # type: ignore[arg-type]
            repository=_FakeCache(),  # type: ignore[arg-type]
        )

        result = await router.analyze(_image_bytes())

        self.assertEqual(VisionRoute.PRO, result.route)
        self.assertEqual((VisionRoute.FLASH, VisionRoute.PRO), result.attempts)
        self.assertEqual(1, pro.calls)
        self.assertEqual(0, sensitive.calls)
        self.assertEqual("flash_refusal", result.metadata["fallback_reason"])

    async def test_flash_refusal_without_pro_never_calls_sensitive(self) -> None:
        flash = _FakeClient(
            VisionRoute.FLASH,
            error=VisionAnalysisError("provider refusal: content policy"),
        )
        sensitive = _FakeClient(VisionRoute.SENSITIVE)
        router = VisionCascadeRouter(
            flash=flash,  # type: ignore[arg-type]
            sensitive=sensitive,  # type: ignore[arg-type]
            repository=_FakeCache(),  # type: ignore[arg-type]
        )

        with self.assertRaisesRegex(VisionAnalysisError, "provider refusal"):
            await router.analyze(_image_bytes())

        self.assertEqual(0, sensitive.calls)

    async def test_sensitive_requires_explicit_adult_confirmation(self) -> None:
        sensitive = _FakeClient(VisionRoute.SENSITIVE)
        cache = _FakeCache()
        router = VisionCascadeRouter(
            flash=_FakeClient(VisionRoute.FLASH),  # type: ignore[arg-type]
            sensitive=sensitive,  # type: ignore[arg-type]
            repository=cache,  # type: ignore[arg-type]
        )

        with self.assertRaisesRegex(VisionAnalysisError, "adult_confirmed=true"):
            await router.analyze(_image_bytes(), sensitive=True)

        self.assertEqual(0, sensitive.calls)
        self.assertEqual([], cache.find_calls)

    async def test_explicit_sensitive_skips_flash_and_pro(self) -> None:
        flash = _FakeClient(VisionRoute.FLASH)
        pro = _FakeClient(VisionRoute.PRO)
        sensitive = _FakeClient(VisionRoute.SENSITIVE, confidence=80)
        cache = _FakeCache()
        router = VisionCascadeRouter(
            flash=flash,  # type: ignore[arg-type]
            pro=pro,  # type: ignore[arg-type]
            sensitive=sensitive,  # type: ignore[arg-type]
            repository=cache,  # type: ignore[arg-type]
        )

        result = await router.analyze(
            _image_bytes(),
            sensitive=True,
            adult_confirmed=True,
        )

        self.assertEqual(VisionRoute.SENSITIVE, result.route)
        self.assertEqual((VisionRoute.SENSITIVE,), result.attempts)
        self.assertEqual(0, flash.calls)
        self.assertEqual(0, pro.calls)
        self.assertEqual(1, sensitive.calls)
        self.assertTrue(result.metadata["adult_confirmed"])
        self.assertIn(":sensitive", cache.find_calls[0]["analysis_type"])
        self.assertEqual(("sensitive-model",), cache.find_calls[0]["models"])

    async def test_low_confidence_sensitive_requires_manual_review(self) -> None:
        sensitive = _FakeClient(VisionRoute.SENSITIVE, confidence=41)
        router = VisionCascadeRouter(
            flash=_FakeClient(VisionRoute.FLASH),  # type: ignore[arg-type]
            sensitive=sensitive,  # type: ignore[arg-type]
            repository=_FakeCache(),  # type: ignore[arg-type]
            confidence_threshold=70,
        )

        result = await router.analyze(
            _image_bytes(),
            sensitive=True,
            adult_confirmed=True,
        )

        self.assertTrue(result.metadata["manual_review_required"])
        self.assertEqual(
            "low_sensitive_confidence",
            result.metadata["manual_review_reason"],
        )

    async def test_standard_cache_key_excludes_sensitive_model(self) -> None:
        cache = _FakeCache()
        router = VisionCascadeRouter(
            flash=_FakeClient(VisionRoute.FLASH),  # type: ignore[arg-type]
            pro=_FakeClient(VisionRoute.PRO),  # type: ignore[arg-type]
            sensitive=_FakeClient(VisionRoute.SENSITIVE),  # type: ignore[arg-type]
            repository=cache,  # type: ignore[arg-type]
        )

        await router.analyze(_image_bytes())

        self.assertEqual(
            ("flash-model", "pro-model"),
            cache.find_calls[0]["models"],
        )
        self.assertIn(":standard", cache.find_calls[0]["analysis_type"])

    async def test_cache_hit_skips_all_provider_calls(self) -> None:
        cached = CachedVisionAnalysis(
            cache_id=7,
            content_hash="a" * 64,
            analysis_type="semantic-profile:schema-1:standard",
            prompt_version=1,
            route=VisionRoute.PRO,
            provider="cached-provider",
            model="pro-model",
            profile=_profile(93),
            confidence=93,
            input_tokens=120,
            output_tokens=60,
            actual_cost_rub=Decimal("0.42"),
        )
        flash = _FakeClient(VisionRoute.FLASH)
        pro = _FakeClient(VisionRoute.PRO)
        cache = _FakeCache(cached)
        router = VisionCascadeRouter(
            flash=flash,  # type: ignore[arg-type]
            pro=pro,  # type: ignore[arg-type]
            repository=cache,  # type: ignore[arg-type]
        )

        result = await router.analyze(_image_bytes())

        self.assertTrue(result.cache_hit)
        self.assertEqual(VisionRoute.PRO, result.route)
        self.assertEqual((), result.attempts)
        self.assertEqual(0, flash.calls)
        self.assertEqual(0, pro.calls)
        self.assertEqual([], cache.stored)
        self.assertEqual("standard", result.metadata["analysis_mode"])

    async def test_pro_error_uses_valid_flash_result(self) -> None:
        flash = _FakeClient(VisionRoute.FLASH, confidence=45)
        pro = _FakeClient(VisionRoute.PRO, error=VisionAnalysisError("bad json"))
        sensitive = _FakeClient(VisionRoute.SENSITIVE)
        router = VisionCascadeRouter(
            flash=flash,  # type: ignore[arg-type]
            pro=pro,  # type: ignore[arg-type]
            sensitive=sensitive,  # type: ignore[arg-type]
            repository=_FakeCache(),  # type: ignore[arg-type]
        )

        result = await router.analyze(_image_bytes())

        self.assertEqual(VisionRoute.FLASH, result.route)
        self.assertEqual("pro_error_use_flash", result.metadata["fallback_reason"])
        self.assertEqual(0, sensitive.calls)


if __name__ == "__main__":
    unittest.main()

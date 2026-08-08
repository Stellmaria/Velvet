from __future__ import annotations

import io
import unittest
from decimal import Decimal
from typing import Any, Mapping

from PIL import Image

from velvet_bot.ai_vision import VisionAnalysisError
from velvet_bot.domains.vision_routing.failures import VisionRefusalError
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
        model: str | None = None,
    ) -> None:
        self.route = route
        self.provider = "test-provider"
        self.model = model or f"{route.value}-model"
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
    async def test_high_confidence_main_does_not_call_pro(self) -> None:
        main = _FakeClient(VisionRoute.FLASH, confidence=88)
        pro = _FakeClient(VisionRoute.PRO, confidence=96)
        cache = _FakeCache()
        router = VisionCascadeRouter(
            flash=main,  # type: ignore[arg-type]
            pro=pro,  # type: ignore[arg-type]
            repository=cache,  # type: ignore[arg-type]
            confidence_threshold=70,
        )

        result = await router.analyze(_image_bytes())

        self.assertEqual(VisionRoute.FLASH, result.route)
        self.assertEqual((VisionRoute.FLASH,), result.attempts)
        self.assertEqual(1, main.calls)
        self.assertEqual(0, pro.calls)
        self.assertEqual(1, len(cache.stored))
        self.assertEqual("standard", result.metadata["analysis_mode"])

    async def test_low_confidence_main_calls_pro(self) -> None:
        main = _FakeClient(VisionRoute.FLASH, confidence=42)
        pro = _FakeClient(VisionRoute.PRO, confidence=91)
        router = VisionCascadeRouter(
            flash=main,  # type: ignore[arg-type]
            pro=pro,  # type: ignore[arg-type]
            repository=_FakeCache(),  # type: ignore[arg-type]
            confidence_threshold=70,
        )

        result = await router.analyze(_image_bytes())

        self.assertEqual(VisionRoute.PRO, result.route)
        self.assertEqual((VisionRoute.FLASH, VisionRoute.PRO), result.attempts)
        self.assertEqual("low_confidence", result.metadata["fallback_reason"])

    async def test_standard_main_refusal_uses_pro_not_uncensored(self) -> None:
        main = _FakeClient(
            VisionRoute.FLASH,
            error=VisionRefusalError("blocked by content policy"),
        )
        pro = _FakeClient(VisionRoute.PRO, confidence=84)
        uncensored = _FakeClient(VisionRoute.SENSITIVE, confidence=99)
        router = VisionCascadeRouter(
            flash=main,  # type: ignore[arg-type]
            pro=pro,  # type: ignore[arg-type]
            sensitive=uncensored,  # type: ignore[arg-type]
            repository=_FakeCache(),  # type: ignore[arg-type]
        )

        result = await router.analyze(_image_bytes())

        self.assertEqual(VisionRoute.PRO, result.route)
        self.assertEqual((VisionRoute.FLASH, VisionRoute.PRO), result.attempts)
        self.assertEqual(1, pro.calls)
        self.assertEqual(0, uncensored.calls)
        self.assertEqual("main_refusal", result.metadata["fallback_reason"])

    async def test_standard_refusal_without_pro_never_calls_uncensored(self) -> None:
        main = _FakeClient(
            VisionRoute.FLASH,
            error=VisionRefusalError("content policy"),
        )
        uncensored = _FakeClient(VisionRoute.SENSITIVE)
        router = VisionCascadeRouter(
            flash=main,  # type: ignore[arg-type]
            sensitive=uncensored,  # type: ignore[arg-type]
            repository=_FakeCache(),  # type: ignore[arg-type]
        )

        with self.assertRaises(VisionRefusalError):
            await router.analyze(_image_bytes())

        self.assertEqual(0, uncensored.calls)

    async def test_sensitive_requires_explicit_adult_confirmation(self) -> None:
        main = _FakeClient(VisionRoute.FLASH)
        uncensored = _FakeClient(VisionRoute.SENSITIVE)
        cache = _FakeCache()
        router = VisionCascadeRouter(
            flash=main,  # type: ignore[arg-type]
            sensitive=uncensored,  # type: ignore[arg-type]
            repository=cache,  # type: ignore[arg-type]
        )

        with self.assertRaisesRegex(VisionAnalysisError, "adult_confirmed=true"):
            await router.analyze(_image_bytes(), sensitive=True)

        self.assertEqual(0, main.calls)
        self.assertEqual(0, uncensored.calls)
        self.assertEqual([], cache.find_calls)

    async def test_sensitive_high_confidence_uses_main_first_and_stops(self) -> None:
        standard_main = _FakeClient(VisionRoute.FLASH, model="main-model")
        sensitive_main = _FakeClient(
            VisionRoute.FLASH,
            confidence=88,
            model="main-model",
        )
        pro = _FakeClient(VisionRoute.PRO)
        uncensored = _FakeClient(VisionRoute.SENSITIVE, confidence=99)
        cache = _FakeCache()
        router = VisionCascadeRouter(
            flash=standard_main,  # type: ignore[arg-type]
            main_sensitive=sensitive_main,  # type: ignore[arg-type]
            pro=pro,  # type: ignore[arg-type]
            sensitive=uncensored,  # type: ignore[arg-type]
            repository=cache,  # type: ignore[arg-type]
        )

        result = await router.analyze(
            _image_bytes(),
            sensitive=True,
            adult_confirmed=True,
        )

        self.assertEqual(VisionRoute.FLASH, result.route)
        self.assertEqual((VisionRoute.FLASH,), result.attempts)
        self.assertEqual(0, standard_main.calls)
        self.assertEqual(1, sensitive_main.calls)
        self.assertEqual(0, pro.calls)
        self.assertEqual(0, uncensored.calls)
        self.assertFalse(result.metadata["uncensored_required"])
        self.assertEqual(("main-model", "sensitive-model"), cache.find_calls[0]["models"])

    async def test_sensitive_low_confidence_main_calls_uncensored(self) -> None:
        standard_main = _FakeClient(VisionRoute.FLASH, model="main-model")
        sensitive_main = _FakeClient(
            VisionRoute.FLASH,
            confidence=41,
            model="main-model",
        )
        uncensored = _FakeClient(VisionRoute.SENSITIVE, confidence=82)
        pro = _FakeClient(VisionRoute.PRO)
        router = VisionCascadeRouter(
            flash=standard_main,  # type: ignore[arg-type]
            main_sensitive=sensitive_main,  # type: ignore[arg-type]
            pro=pro,  # type: ignore[arg-type]
            sensitive=uncensored,  # type: ignore[arg-type]
            repository=_FakeCache(),  # type: ignore[arg-type]
            confidence_threshold=70,
        )

        result = await router.analyze(
            _image_bytes(),
            sensitive=True,
            adult_confirmed=True,
        )

        self.assertEqual(VisionRoute.SENSITIVE, result.route)
        self.assertEqual((VisionRoute.FLASH, VisionRoute.SENSITIVE), result.attempts)
        self.assertEqual("low_sensitive_confidence", result.metadata["fallback_reason"])
        self.assertEqual(0, pro.calls)

    async def test_sensitive_main_refusal_calls_uncensored_not_pro(self) -> None:
        standard_main = _FakeClient(VisionRoute.FLASH, model="main-model")
        sensitive_main = _FakeClient(
            VisionRoute.FLASH,
            error=VisionRefusalError("blocked"),
            model="main-model",
        )
        uncensored = _FakeClient(VisionRoute.SENSITIVE, confidence=85)
        pro = _FakeClient(VisionRoute.PRO)
        router = VisionCascadeRouter(
            flash=standard_main,  # type: ignore[arg-type]
            main_sensitive=sensitive_main,  # type: ignore[arg-type]
            pro=pro,  # type: ignore[arg-type]
            sensitive=uncensored,  # type: ignore[arg-type]
            repository=_FakeCache(),  # type: ignore[arg-type]
        )

        result = await router.analyze(
            _image_bytes(),
            sensitive=True,
            adult_confirmed=True,
        )

        self.assertEqual(VisionRoute.SENSITIVE, result.route)
        self.assertEqual("main_refusal", result.metadata["fallback_reason"])
        self.assertEqual(0, pro.calls)
        self.assertEqual(1, uncensored.calls)

    async def test_low_confidence_sensitive_without_uncensored_returns_main_for_review(self) -> None:
        main = _FakeClient(VisionRoute.FLASH, confidence=41)
        router = VisionCascadeRouter(
            flash=main,  # type: ignore[arg-type]
            repository=_FakeCache(),  # type: ignore[arg-type]
            confidence_threshold=70,
        )

        result = await router.analyze(
            _image_bytes(),
            sensitive=True,
            adult_confirmed=True,
        )

        self.assertEqual(VisionRoute.FLASH, result.route)
        self.assertTrue(result.metadata["manual_review_required"])
        self.assertEqual(
            "low_sensitive_confidence",
            result.metadata["manual_review_reason"],
        )

    async def test_force_pro_still_runs_main_first(self) -> None:
        main = _FakeClient(VisionRoute.FLASH, confidence=99)
        pro = _FakeClient(VisionRoute.PRO, confidence=95)
        cache = _FakeCache()
        router = VisionCascadeRouter(
            flash=main,  # type: ignore[arg-type]
            pro=pro,  # type: ignore[arg-type]
            repository=cache,  # type: ignore[arg-type]
        )

        result = await router.analyze(_image_bytes(), force_pro=True)

        self.assertEqual((VisionRoute.FLASH, VisionRoute.PRO), result.attempts)
        self.assertEqual("owner_force_pro", result.metadata["fallback_reason"])
        self.assertIn(":force-pro", cache.find_calls[0]["analysis_type"])

    async def test_force_pro_is_forbidden_for_sensitive(self) -> None:
        cache = _FakeCache()
        router = VisionCascadeRouter(
            flash=_FakeClient(VisionRoute.FLASH),  # type: ignore[arg-type]
            pro=_FakeClient(VisionRoute.PRO),  # type: ignore[arg-type]
            repository=cache,  # type: ignore[arg-type]
        )

        with self.assertRaisesRegex(VisionAnalysisError, "никогда"):
            await router.analyze(
                _image_bytes(),
                sensitive=True,
                adult_confirmed=True,
                force_pro=True,
            )
        self.assertEqual([], cache.find_calls)

    async def test_force_uncensored_is_forbidden_for_standard(self) -> None:
        router = VisionCascadeRouter(
            flash=_FakeClient(VisionRoute.FLASH),  # type: ignore[arg-type]
            sensitive=_FakeClient(VisionRoute.SENSITIVE),  # type: ignore[arg-type]
            repository=_FakeCache(),  # type: ignore[arg-type]
        )

        with self.assertRaisesRegex(VisionAnalysisError, "только"):
            await router.analyze(_image_bytes(), force_uncensored=True)

    async def test_force_uncensored_runs_sensitive_main_then_uncensored(self) -> None:
        standard_main = _FakeClient(VisionRoute.FLASH, model="main-model")
        sensitive_main = _FakeClient(
            VisionRoute.FLASH,
            confidence=99,
            model="main-model",
        )
        uncensored = _FakeClient(VisionRoute.SENSITIVE, confidence=90)
        cache = _FakeCache()
        router = VisionCascadeRouter(
            flash=standard_main,  # type: ignore[arg-type]
            main_sensitive=sensitive_main,  # type: ignore[arg-type]
            sensitive=uncensored,  # type: ignore[arg-type]
            repository=cache,  # type: ignore[arg-type]
        )

        result = await router.analyze(
            _image_bytes(),
            sensitive=True,
            adult_confirmed=True,
            force_uncensored=True,
        )

        self.assertEqual((VisionRoute.FLASH, VisionRoute.SENSITIVE), result.attempts)
        self.assertEqual("owner_force_uncensored", result.metadata["fallback_reason"])
        self.assertIn(":force-uncensored", cache.find_calls[0]["analysis_type"])

    async def test_standard_cache_key_excludes_uncensored_model(self) -> None:
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
        main = _FakeClient(VisionRoute.FLASH)
        pro = _FakeClient(VisionRoute.PRO)
        cache = _FakeCache(cached)
        router = VisionCascadeRouter(
            flash=main,  # type: ignore[arg-type]
            pro=pro,  # type: ignore[arg-type]
            repository=cache,  # type: ignore[arg-type]
        )

        result = await router.analyze(_image_bytes())

        self.assertTrue(result.cache_hit)
        self.assertEqual(VisionRoute.PRO, result.route)
        self.assertEqual((), result.attempts)
        self.assertEqual(0, main.calls)
        self.assertEqual(0, pro.calls)
        self.assertEqual([], cache.stored)
        self.assertEqual("standard", result.metadata["analysis_mode"])

    async def test_pro_error_uses_valid_main_result(self) -> None:
        main = _FakeClient(VisionRoute.FLASH, confidence=45)
        pro = _FakeClient(VisionRoute.PRO, error=VisionAnalysisError("bad json"))
        uncensored = _FakeClient(VisionRoute.SENSITIVE)
        router = VisionCascadeRouter(
            flash=main,  # type: ignore[arg-type]
            pro=pro,  # type: ignore[arg-type]
            sensitive=uncensored,  # type: ignore[arg-type]
            repository=_FakeCache(),  # type: ignore[arg-type]
        )

        result = await router.analyze(_image_bytes())

        self.assertEqual(VisionRoute.FLASH, result.route)
        self.assertEqual("pro_error_use_main", result.metadata["fallback_reason"])
        self.assertEqual(0, uncensored.calls)


if __name__ == "__main__":
    unittest.main()

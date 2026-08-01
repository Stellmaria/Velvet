from __future__ import annotations

import unittest

from velvet_bot.ai_vision import VisionAnalysisError
from velvet_bot.domains.vision_routing.models import VisionAnalysisMode
from velvet_bot.domains.vision_routing.profile_contract import (
    PROFILE_SCHEMA_VERSION,
    SENSITIVE_PROFILE_SCHEMA,
    STANDARD_PROFILE_SCHEMA,
    normalize_routed_profile,
    prompt_for_mode,
)


def _payload(
    mode: VisionAnalysisMode,
    *,
    prompt_version: int = 3,
    content_mode: str | None = None,
) -> dict[str, object]:
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "prompt_version": prompt_version,
        "route": mode.value,
        "content_mode": content_mode
        or ("adult_editorial" if mode is VisionAnalysisMode.SENSITIVE else "editorial"),
        "series_title_ru": "Тестовый сет",
        "summary_ru": "Только видимые факты.",
        "themes": ["editorial"],
        "genres": [],
        "settings": ["studio"],
        "eras": [],
        "environment": ["studio"],
        "objects": [],
        "wardrobe": [],
        "composition": ["full body"],
        "lighting": ["soft light"],
        "palette": ["black"],
        "mood": ["calm"],
        "actions": [],
        "series_keywords": ["editorial", "studio"],
        "people_count": 1,
        "confidence": 88,
        "structured": {
            "subjects": [{"position": "center"}],
            "composition": {"framing": "full body"},
            "pose": {"body": "standing"},
            "camera": {"angle": "eye level"},
            "body_visibility": {"torso": "visible"},
            "covering_method": {},
            "environment": {"location": "studio"},
            "lighting": {"type": "soft"},
            "visible_text": [],
            "uncertainties": [],
            "generation_risks": [],
        },
    }


class VisionProfileContractTests(unittest.TestCase):
    def test_standard_and_sensitive_schemas_are_route_specific(self) -> None:
        standard_route = STANDARD_PROFILE_SCHEMA["properties"]["route"]
        sensitive_route = SENSITIVE_PROFILE_SCHEMA["properties"]["route"]
        self.assertEqual("standard", standard_route["const"])
        self.assertEqual("sensitive", sensitive_route["const"])
        self.assertNotEqual(
            STANDARD_PROFILE_SCHEMA["properties"]["content_mode"]["enum"],
            SENSITIVE_PROFILE_SCHEMA["properties"]["content_mode"]["enum"],
        )

    def test_prompts_are_separate_and_sensitive_does_not_guess_age(self) -> None:
        standard = prompt_for_mode(VisionAnalysisMode.STANDARD)
        sensitive = prompt_for_mode(VisionAnalysisMode.SENSITIVE)
        self.assertNotEqual(standard, sensitive)
        self.assertIn("route должен быть standard", standard)
        self.assertIn("route должен быть sensitive", sensitive)
        self.assertIn("Не пытайся определять или угадывать возраст", sensitive)

    def test_normalizes_valid_sensitive_profile(self) -> None:
        profile = normalize_routed_profile(
            _payload(VisionAnalysisMode.SENSITIVE),
            mode=VisionAnalysisMode.SENSITIVE,
            prompt_version=3,
        )

        self.assertEqual("sensitive", profile["route"])
        self.assertEqual("adult_editorial", profile["content_mode"])
        self.assertEqual(PROFILE_SCHEMA_VERSION, profile["schema_version"])
        self.assertEqual(3, profile["prompt_version"])
        self.assertEqual("center", profile["structured"]["subjects"][0]["position"])

    def test_rejects_wrong_route_instead_of_silently_rewriting_it(self) -> None:
        payload = _payload(VisionAnalysisMode.STANDARD)
        payload["route"] = "sensitive"

        with self.assertRaisesRegex(VisionAnalysisError, "route"):
            normalize_routed_profile(
                payload,
                mode=VisionAnalysisMode.STANDARD,
                prompt_version=3,
            )

    def test_rejects_wrong_prompt_version(self) -> None:
        with self.assertRaisesRegex(VisionAnalysisError, "prompt_version"):
            normalize_routed_profile(
                _payload(VisionAnalysisMode.STANDARD, prompt_version=2),
                mode=VisionAnalysisMode.STANDARD,
                prompt_version=3,
            )

    def test_rejects_missing_structured_field(self) -> None:
        payload = _payload(VisionAnalysisMode.SENSITIVE)
        structured = payload["structured"]
        assert isinstance(structured, dict)
        structured.pop("uncertainties")

        with self.assertRaisesRegex(VisionAnalysisError, "uncertainties"):
            normalize_routed_profile(
                payload,
                mode=VisionAnalysisMode.SENSITIVE,
                prompt_version=3,
            )

    def test_standard_route_rejects_adult_content_mode(self) -> None:
        with self.assertRaisesRegex(VisionAnalysisError, "content_mode"):
            normalize_routed_profile(
                _payload(
                    VisionAnalysisMode.STANDARD,
                    content_mode="explicit_adult",
                ),
                mode=VisionAnalysisMode.STANDARD,
                prompt_version=3,
            )


if __name__ == "__main__":
    unittest.main()

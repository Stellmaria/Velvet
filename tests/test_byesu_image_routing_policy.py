from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODERS = ROOT / "deploy" / "hermes-coders"
if str(CODERS) not in sys.path:
    sys.path.insert(0, str(CODERS))

import byesu_image_fallback as base  # noqa: E402
import byesu_image_routing_policy as policy  # noqa: E402


class ByesuImageRoutingPolicyTests(unittest.TestCase):
    def test_cheap_model_requires_1k_and_at_most_three_references(self) -> None:
        for reference_count in range(4):
            self.assertEqual(
                policy.select_image_model("1K", reference_count),
                "gpt-image-2",
            )
        self.assertEqual(
            policy.select_image_model("1K", 4),
            "firefly-gpt-image-2",
        )
        self.assertEqual(
            policy.select_image_model("1K", 6),
            "firefly-gpt-image-2",
        )

    def test_any_higher_quality_uses_extended_model(self) -> None:
        for resolution in ("2K", "4K"):
            for reference_count in (0, 1, 3, 6):
                self.assertEqual(
                    policy.select_image_model(resolution, reference_count),
                    "firefly-gpt-image-2",
                )

    def test_reference_limit_is_strictly_six(self) -> None:
        with self.assertRaises(base.ByesuImageFallbackError):
            policy.select_image_model("1K", 7)

    def test_codex_primary_is_used_only_for_1k(self) -> None:
        self.assertTrue(policy.uses_codex_primary("1K"))
        self.assertFalse(policy.uses_codex_primary("2K"))
        self.assertFalse(policy.uses_codex_primary("4K"))

    def test_analysis_contract_builds_one_compact_prompt_without_chinese_trick(self) -> None:
        source = inspect.getsource(policy.RoutedByesuImageClient.analyze)
        self.assertIn("финальный prompt", source)
        self.assertIn("Не переводи промт на китайский", source)
        self.assertIn("_MAX_GENERATION_PROMPT_CHARS", source)
        self.assertNotIn("text = text[:", source)

    def test_runtime_policy_patches_six_reference_eight_megabyte_contract(self) -> None:
        source = inspect.getsource(policy.install_byesu_image_routing_policy)
        self.assertIn("MAX_IMAGE_REFERENCES = _MAX_REFERENCES", source)
        self.assertIn("MAX_IMAGE_REFERENCE_BYTES = _MAX_REFERENCE_BYTES", source)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from velvet_bot.prompt_result_comparison import normalize_prompt_result_comparison


class PromptResultComparisonNormalizationTests(unittest.TestCase):
    @staticmethod
    def payload() -> dict[str, object]:
        return {
            "overall_score": 88,
            "subject_score": 91,
            "composition_score": 86,
            "lighting_score": 90,
            "palette_score": 84,
            "environment_score": 82,
            "style_score": 89,
            "technical_score": 87,
            "confidence": 78,
            "verdict": "strong",
            "summary_ru": "Основные требования выполнены.",
            "matched_requirements": ["Сохранён контровой свет."],
            "violated_requirements": [],
            "uncertain_requirements": [],
            "extra_elements": [],
            "priorities": [],
        }

    def test_clean_high_score_is_strong(self) -> None:
        report = normalize_prompt_result_comparison(self.payload())

        self.assertEqual("strong", report["verdict"])
        self.assertEqual(88, report["overall_score"])
        self.assertEqual(["Сохранён контровой свет."], report["matched_requirements"])

    def test_visible_violation_prevents_strong_verdict(self) -> None:
        payload = self.payload()
        payload["violated_requirements"] = ["Камера расположена не с того угла."]

        report = normalize_prompt_result_comparison(payload)

        self.assertEqual("partial", report["verdict"])

    def test_low_confidence_is_insufficient_and_scores_are_clamped(self) -> None:
        payload = self.payload()
        payload["confidence"] = 12
        payload["palette_score"] = 180
        payload["technical_score"] = -20

        report = normalize_prompt_result_comparison(payload)

        self.assertEqual("insufficient", report["verdict"])
        self.assertEqual(100, report["palette_score"])
        self.assertEqual(0, report["technical_score"])

    def test_duplicate_notes_are_removed(self) -> None:
        payload = self.payload()
        payload["priorities"] = ["Исправить свет.", "Исправить свет."]

        report = normalize_prompt_result_comparison(payload)

        self.assertEqual(["Исправить свет."], report["priorities"])


if __name__ == "__main__":
    unittest.main()

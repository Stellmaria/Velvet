from __future__ import annotations

import unittest

from velvet_bot.ai_quality import AIQualityItem, normalize_quality_report
from velvet_bot.presentation.telegram.routers.quality_operations_controllers.quality_ai import _report_text


class AIQualityNormalizationTests(unittest.TestCase):
    def test_critical_issue_forces_critical_verdict(self) -> None:
        report = normalize_quality_report(
            {
                "quality_score": 74,
                "confidence": 88,
                "verdict": "ready",
                "summary_ru": "Есть проблема с рукой.",
                "critical_issues": ["Левая кисть содержит лишний палец."],
                "warnings": [],
                "strengths": ["Свет согласован."],
                "uncertain_areas": [],
                "checks": {"hands": 20, "lighting": 95},
            }
        )

        self.assertEqual(report["verdict"], "critical")
        self.assertEqual(report["quality_score"], 74)
        self.assertEqual(report["checks"]["hands"], 20)
        self.assertEqual(report["checks"]["lighting"], 95)
        self.assertIn("anatomy", report["checks"])

    def test_warning_forces_manual_review_and_clamps_scores(self) -> None:
        report = normalize_quality_report(
            {
                "quality_score": 170,
                "confidence": -5,
                "verdict": "ready",
                "summary_ru": "  Небольшой шум в тенях.  ",
                "critical_issues": [],
                "warnings": ["Шум в тенях."],
                "strengths": [],
                "uncertain_areas": [],
                "checks": {"sharpness": 120, "background": -20},
            }
        )

        self.assertEqual(report["verdict"], "review")
        self.assertEqual(report["quality_score"], 100)
        self.assertEqual(report["confidence"], 50)
        self.assertEqual(report["checks"]["sharpness"], 100)
        self.assertEqual(report["checks"]["background"], 0)

    def test_empty_findings_are_ready(self) -> None:
        report = normalize_quality_report(
            {
                "quality_score": 92,
                "confidence": 81,
                "verdict": "critical",
                "summary_ru": "",
                "critical_issues": [],
                "warnings": [],
                "strengths": [],
                "uncertain_areas": [],
                "checks": {},
            }
        )

        self.assertEqual(report["verdict"], "ready")
        self.assertIn("Явных", report["summary_ru"])


class AIQualityRenderingTests(unittest.TestCase):
    def test_report_renders_owner_decision_and_findings(self) -> None:
        item = AIQualityItem(
            media_id=42,
            file_name="example.jpg",
            media_type="photo",
            telegram_file_id="file-id",
            preview_file_id=None,
            status="ready",
            verdict="review",
            quality_score=79,
            confidence=84,
            report={
                "summary_ru": "Нужна ручная проверка.",
                "critical_issues": [],
                "warnings": ["Кожа чрезмерно сглажена."],
                "strengths": ["Хороший свет."],
                "uncertain_areas": [],
                "checks": {"skin_texture": 54, "lighting": 91},
            },
            decision="fix_required",
            error_message=None,
        )

        rendered = _report_text(item)

        self.assertIn("media #42", rendered)
        self.assertIn("отправлено на исправление", rendered)
        self.assertIn("Кожа чрезмерно сглажена", rendered)
        self.assertIn("Текстура кожи", rendered)


if __name__ == "__main__":
    unittest.main()

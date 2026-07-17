from __future__ import annotations

import unittest

from velvet_bot.reference_comparison import normalize_reference_comparison


class ReferenceComparisonNormalizationTests(unittest.TestCase):
    def _payload(self) -> dict[str, object]:
        return {
            "overall_score": 88,
            "face_score": 92,
            "hair_score": 86,
            "body_score": 81,
            "unique_traits_score": 84,
            "confidence": 79,
            "verdict": "strong",
            "summary_ru": "Основные видимые черты сохранены.",
            "face_matches": ["Совпадает форма лица."],
            "face_differences": [],
            "hair_matches": ["Сохранены цвет и длина волос."],
            "hair_differences": [],
            "body_matches": ["Сходная ширина плеч."],
            "body_differences": [],
            "unique_matches": ["Видимая татуировка сохранена."],
            "unique_differences": [],
            "uncertain_areas": [],
            "visibility": {
                "reference_face": 95,
                "result_face": 92,
                "reference_body": 80,
                "result_body": 76,
                "reference_unique_traits": 70,
                "result_unique_traits": 68,
            },
        }

    def test_high_scores_produce_strong_visual_match(self) -> None:
        report = normalize_reference_comparison(self._payload())

        self.assertEqual("strong", report["verdict"])
        self.assertEqual(88, report["overall_score"])
        self.assertEqual(92, report["face_score"])
        self.assertEqual([], report["face_differences"])

    def test_low_visibility_prevents_false_confidence(self) -> None:
        payload = self._payload()
        payload["overall_score"] = 91
        payload["visibility"] = {
            "reference_face": 20,
            "result_face": 15,
            "reference_body": 25,
            "result_body": 10,
            "reference_unique_traits": 5,
            "result_unique_traits": 0,
        }

        report = normalize_reference_comparison(payload)

        self.assertEqual("insufficient", report["verdict"])
        self.assertTrue(
            any("Телосложение" in value for value in report["uncertain_areas"])
        )
        self.assertTrue(
            any("Уникальные признаки" in value for value in report["uncertain_areas"])
        )

    def test_scores_are_clamped_and_duplicate_notes_removed(self) -> None:
        payload = self._payload()
        payload["face_score"] = 145
        payload["body_score"] = -20
        payload["face_matches"] = ["Совпадает нос.", "Совпадает нос."]

        report = normalize_reference_comparison(payload)

        self.assertEqual(100, report["face_score"])
        self.assertEqual(0, report["body_score"])
        self.assertEqual(["Совпадает нос."], report["face_matches"])


if __name__ == "__main__":
    unittest.main()

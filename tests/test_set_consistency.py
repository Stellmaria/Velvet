from __future__ import annotations

import io
import unittest

from PIL import Image

from velvet_bot.set_consistency import (
    SetConsistencyInput,
    build_contact_sheet,
    normalize_set_consistency,
)


class SetConsistencyNormalizationTests(unittest.TestCase):
    def _payload(self, count: int = 3) -> dict[str, object]:
        return {
            "overall_score": 91,
            "style_score": 93,
            "lighting_score": 89,
            "palette_score": 92,
            "environment_score": 88,
            "composition_score": 90,
            "narrative_score": 86,
            "character_continuity_score": 94,
            "technical_score": 90,
            "confidence": 84,
            "verdict": "coherent",
            "summary_ru": "Кадры образуют единую серию.",
            "shared_traits": ["Единая холодная палитра."],
            "set_issues": [],
            "uncertain_areas": [],
            "items": [
                {
                    "index": index,
                    "consistency_score": 88 + index,
                    "status": "core",
                    "reasons": ["Поддерживает общий стиль."],
                }
                for index in range(1, count + 1)
            ],
        }

    def test_consistent_set_remains_coherent_and_maps_media_ids(self) -> None:
        report = normalize_set_consistency(self._payload(), (101, 102, 103))

        self.assertEqual("coherent", report["verdict"])
        self.assertEqual([101, 102, 103], [item["media_id"] for item in report["items"]])
        self.assertEqual(91, report["overall_score"])

    def test_low_scored_core_item_is_normalized_to_outlier(self) -> None:
        payload = self._payload()
        payload["items"][1]["consistency_score"] = 31  # type: ignore[index]
        payload["items"][1]["status"] = "core"  # type: ignore[index]

        report = normalize_set_consistency(payload, (101, 102, 103))

        self.assertEqual("review", report["verdict"])
        self.assertEqual("outlier", report["items"][1]["status"])
        self.assertEqual(102, report["items"][1]["media_id"])

    def test_many_outliers_force_incoherent_verdict(self) -> None:
        payload = self._payload(count=5)
        for index in (0, 1):
            payload["items"][index]["status"] = "outlier"  # type: ignore[index]
            payload["items"][index]["consistency_score"] = 40  # type: ignore[index]

        report = normalize_set_consistency(payload, (11, 12, 13, 14, 15))

        self.assertEqual("incoherent", report["verdict"])

    def test_missing_half_of_item_results_force_insufficient_verdict(self) -> None:
        payload = self._payload(count=4)
        payload["items"] = payload["items"][:2]  # type: ignore[index]

        report = normalize_set_consistency(payload, (1, 2, 3, 4))

        self.assertEqual("insufficient", report["verdict"])
        self.assertEqual("uncertain", report["items"][2]["status"])
        self.assertEqual("uncertain", report["items"][3]["status"])

    def test_low_confidence_prevents_false_positive(self) -> None:
        payload = self._payload()
        payload["confidence"] = 20

        report = normalize_set_consistency(payload, (1, 2, 3))

        self.assertEqual("insufficient", report["verdict"])


class SetConsistencyContactSheetTests(unittest.TestCase):
    @staticmethod
    def _image_bytes(size: tuple[int, int], value: int) -> bytes:
        image = Image.new("RGB", size, (value, value, value))
        try:
            output = io.BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()
        finally:
            image.close()

    def test_contact_sheet_contains_all_frames_and_stays_compact(self) -> None:
        items = tuple(
            SetConsistencyInput(
                media_id=900 + index,
                image=self._image_bytes((400 + index, 500), 20 * index),
                characters=(f"Character {index}",),
            )
            for index in range(1, 13)
        )

        sheet = build_contact_sheet(items)

        self.assertTrue(sheet.image.startswith(b"\xff\xd8"))
        self.assertLessEqual(sheet.width, 1280)
        self.assertLessEqual(sheet.height, 1280)
        with Image.open(io.BytesIO(sheet.image)) as opened:
            self.assertEqual((sheet.width, sheet.height), opened.size)

    def test_contact_sheet_requires_at_least_two_images(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "от 2 до 12"):
            build_contact_sheet(
                (
                    SetConsistencyInput(
                        media_id=1,
                        image=self._image_bytes((100, 100), 30),
                    ),
                )
            )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from velvet_bot.ai_vision import (
    build_semantic_reason,
    build_semantic_set_title,
    compare_semantic_profiles,
    normalize_ai_profile,
)


class AIVisionSemanticTests(unittest.TestCase):
    @staticmethod
    def western_profile(*, title: str, setting: str) -> dict:
        return normalize_ai_profile(
            {
                "series_title_ru": title,
                "summary_ru": "Персонаж в атмосфере американского фронтира.",
                "themes": ["wild west", "frontier adventure"],
                "genres": ["western"],
                "settings": [setting, "desert"],
                "eras": ["19th century"],
                "environment": ["dusty landscape"],
                "objects": ["cowboy hat", "horse"],
                "wardrobe": ["western clothing"],
                "composition": ["full body"],
                "lighting": ["golden hour"],
                "palette": ["earth tones"],
                "mood": ["adventurous"],
                "actions": ["standing"],
                "series_keywords": ["western", "cowboy", "frontier"],
                "people_count": 1,
                "confidence": 92,
            }
        )

    def test_different_characters_can_share_one_western_semantic_set(self) -> None:
        first = self.western_profile(title="Дикий Запад", setting="saloon")
        second = self.western_profile(title="Дикий Запад", setting="ranch")

        match = compare_semantic_profiles(first, second)

        self.assertGreaterEqual(match.score, 70)
        self.assertIn("western", match.common_terms)
        self.assertEqual("Дикий Запад", build_semantic_set_title([first, second]))
        self.assertIn("western", build_semantic_reason([first, second]))

    def test_unrelated_fantasy_image_is_not_grouped_with_western(self) -> None:
        western = self.western_profile(title="Дикий Запад", setting="saloon")
        fantasy = normalize_ai_profile(
            {
                "series_title_ru": "Тёмное фэнтези",
                "summary_ru": "Маг в древнем храме.",
                "themes": ["dark fantasy", "magic"],
                "genres": ["fantasy"],
                "settings": ["ancient temple"],
                "eras": ["medieval"],
                "environment": ["stone ruins"],
                "objects": ["spellbook", "candles"],
                "wardrobe": ["mage robes"],
                "composition": ["medium shot"],
                "lighting": ["candlelight"],
                "palette": ["blue and black"],
                "mood": ["mysterious"],
                "actions": ["casting spell"],
                "series_keywords": ["magic", "dark fantasy", "temple"],
                "people_count": 1,
                "confidence": 95,
            }
        )

        self.assertLess(compare_semantic_profiles(western, fantasy).score, 55)

    def test_generic_identity_words_are_removed_from_profile(self) -> None:
        profile = self.western_profile(title="Дикий Запад", setting="saloon")
        profile = normalize_ai_profile(
            {
                **profile,
                "series_keywords": ["person", "woman", "portrait", "wild west"],
            }
        )

        self.assertEqual(["western"], profile["series_keywords"])


if __name__ == "__main__":
    unittest.main()

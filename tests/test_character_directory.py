import unittest

from velvet_bot.character_directory import (
    category_label,
    normalize_category,
    normalize_universe,
    universe_label,
    validate_prompt_post_url,
)


class CharacterCategoryTests(unittest.TestCase):
    def test_russian_categories_are_normalized(self) -> None:
        self.assertEqual("female", normalize_category("женский"))
        self.assertEqual("male", normalize_category("МУЖСКОЙ"))
        self.assertEqual("mf", normalize_category("мж"))
        self.assertEqual("mfm", normalize_category("мжм"))
        self.assertEqual("mfm", normalize_category("MFM"))
        self.assertEqual("mm", normalize_category("мм"))
        self.assertEqual("ff", normalize_category("жж"))

    def test_uncategorized_is_owner_only_option(self) -> None:
        self.assertEqual(
            "uncategorized",
            normalize_category("без", allow_uncategorized=True),
        )
        with self.assertRaises(ValueError):
            normalize_category("без")

    def test_category_label_for_empty_value(self) -> None:
        self.assertEqual("Без категории", category_label(None))

    def test_mfm_category_label(self) -> None:
        self.assertEqual("МЖМ", category_label("mfm"))


class CharacterUniverseTests(unittest.TestCase):
    def test_all_requested_universes_are_normalized(self) -> None:
        expected = {
            "SHS": "shs",
            "КР": "kr",
            "ЛМ": "lm",
            "ИДМ": "idm",
            "BG3": "bg3",
            "Лагерта": "lagerta",
            "Original": "original",
        }
        for raw_value, normalized in expected.items():
            with self.subTest(raw_value=raw_value):
                self.assertEqual(normalized, normalize_universe(raw_value))

    def test_unassigned_is_owner_only_option(self) -> None:
        self.assertEqual(
            "unassigned",
            normalize_universe("без", allow_unassigned=True),
        )
        with self.assertRaises(ValueError):
            normalize_universe("без")

    def test_universe_label_for_empty_value(self) -> None:
        self.assertEqual("Без вселенной", universe_label(None))


class PromptPostUrlTests(unittest.TestCase):
    def test_public_channel_post_url_is_accepted(self) -> None:
        self.assertEqual(
            "https://t.me/velvet_anatomy/123",
            validate_prompt_post_url("https://t.me/velvet_anatomy/123"),
        )

    def test_private_channel_post_url_is_accepted(self) -> None:
        self.assertEqual(
            "https://t.me/c/1234567890/123",
            validate_prompt_post_url("https://t.me/c/1234567890/123"),
        )

    def test_channel_root_without_post_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_prompt_post_url("https://t.me/velvet_anatomy")


if __name__ == "__main__":
    unittest.main()

import unittest

from velvet_bot.character_aliases import normalize_character_alias


class CharacterAliasTests(unittest.TestCase):
    def test_alias_normalization_ignores_case_spaces_and_separators(self) -> None:
        expected = "kaellang"
        self.assertEqual(expected, normalize_character_alias("Kael Lang"))
        self.assertEqual(expected, normalize_character_alias("KAEL_LANG"))
        self.assertEqual(expected, normalize_character_alias("Kael-Lang"))

    def test_cyrillic_alias_is_preserved(self) -> None:
        self.assertEqual("каэльлэнг", normalize_character_alias("Каэль Лэнг"))

    def test_different_short_names_do_not_fuzzy_match(self) -> None:
        self.assertNotEqual(
            normalize_character_alias("Ада"),
            normalize_character_alias("Адам"),
        )


if __name__ == "__main__":
    unittest.main()

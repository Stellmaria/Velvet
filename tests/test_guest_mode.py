import unittest

from velvet_bot.handlers.archive import parse_guest_save_character


class GuestModeCommandTests(unittest.TestCase):
    def test_mention_syntax_is_parsed(self) -> None:
        self.assertEqual(
            "Аид",
            parse_guest_save_character(
                "@dominusVelvetbot save Аид",
                "dominusVelvetbot",
            ),
        )

    def test_command_syntax_is_parsed(self) -> None:
        self.assertEqual(
            "Аид",
            parse_guest_save_character(
                "/save@dominusVelvetbot Аид",
                "dominusVelvetbot",
            ),
        )

    def test_plain_save_is_supported_for_normalized_guest_updates(self) -> None:
        self.assertEqual(
            "Каин",
            parse_guest_save_character(
                "save   Каин",
                "dominusVelvetbot",
            ),
        )

    def test_other_bot_mention_is_rejected(self) -> None:
        self.assertIsNone(
            parse_guest_save_character(
                "@another_bot save Аид",
                "dominusVelvetbot",
            )
        )

    def test_missing_character_name_is_rejected(self) -> None:
        self.assertIsNone(
            parse_guest_save_character(
                "@dominusVelvetbot save",
                "dominusVelvetbot",
            )
        )


if __name__ == "__main__":
    unittest.main()

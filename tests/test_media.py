import unittest

from velvet_bot.media import build_storage_file_name, sanitize_file_name


class MediaFileNameTests(unittest.TestCase):
    def test_same_file_always_gets_same_storage_name(self) -> None:
        first = build_storage_file_name(
            "Каин портрет.png",
            "unique-file-id",
            default_extension=".png",
        )
        second = build_storage_file_name(
            "Каин портрет.png",
            "unique-file-id",
            default_extension=".png",
        )
        self.assertEqual(first, second)

    def test_different_files_with_same_original_name_do_not_collide(self) -> None:
        first = build_storage_file_name(
            "portrait.png",
            "first-unique-id",
            default_extension=".png",
        )
        second = build_storage_file_name(
            "portrait.png",
            "second-unique-id",
            default_extension=".png",
        )
        self.assertNotEqual(first, second)

    def test_windows_reserved_characters_are_removed(self) -> None:
        self.assertEqual("bad_name_.png", sanitize_file_name("bad:name?.png"))

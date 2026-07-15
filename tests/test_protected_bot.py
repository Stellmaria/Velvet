import unittest

from aiogram.methods import SendDocument, SendMessage, SendPhoto

from velvet_bot.protected_bot import protect_private_media_method


class ProtectedMediaBotTests(unittest.TestCase):
    def test_public_private_photo_is_protected(self) -> None:
        method = SendPhoto(chat_id=100, photo="photo-file-id")

        changed = protect_private_media_method(
            method,
            unprotected_private_user_ids={8179531132},
        )

        self.assertTrue(changed)
        self.assertIs(method.protect_content, True)

    def test_allowed_download_recipient_remains_unprotected(self) -> None:
        method = SendDocument(chat_id=8179531132, document="document-file-id")

        changed = protect_private_media_method(
            method,
            unprotected_private_user_ids={8179531132},
        )

        self.assertFalse(changed)
        self.assertIsNot(method.protect_content, True)

    def test_internal_group_media_is_not_changed(self) -> None:
        method = SendPhoto(chat_id=-1001234567890, photo="photo-file-id")

        changed = protect_private_media_method(
            method,
            unprotected_private_user_ids={8179531132},
        )

        self.assertFalse(changed)
        self.assertIsNot(method.protect_content, True)

    def test_text_menu_is_not_protected(self) -> None:
        method = SendMessage(chat_id=100, text="Archive menu")

        changed = protect_private_media_method(
            method,
            unprotected_private_user_ids={8179531132},
        )

        self.assertFalse(changed)


if __name__ == "__main__":
    unittest.main()

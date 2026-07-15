import unittest
from datetime import UTC, datetime

from velvet_bot.database import Character
from velvet_bot.handlers.reference_management import (
    parse_reference_add_character,
    parse_reference_delete_args,
)
from velvet_bot.handlers.references import parse_reference_character
from velvet_bot.reference_catalog import CharacterReference, ReferencePage
from velvet_bot.reference_ui import (
    ReferenceCallback,
    build_reference_delete_keyboard,
    build_reference_keyboard,
)
from velvet_bot.reference_uploads import ReferenceUploadSessions


class ReferenceCommandTests(unittest.TestCase):
    def test_guest_reference_prefix(self) -> None:
        self.assertEqual(
            "Аид",
            parse_reference_character(
                "@dominusVelvetbot ref Аид",
                "dominusVelvetbot",
            ),
        )

    def test_guest_reference_suffix(self) -> None:
        self.assertEqual(
            "Аид",
            parse_reference_character(
                "ref Аид @dominusVelvetbot",
                "dominusVelvetbot",
            ),
        )

    def test_guest_reference_add_prefix(self) -> None:
        self.assertEqual(
            "Аид",
            parse_reference_add_character(
                "@dominusVelvetbot refadd Аид",
                "dominusVelvetbot",
            ),
        )

    def test_other_bot_is_rejected(self) -> None:
        self.assertIsNone(
            parse_reference_character(
                "@another_bot ref Аид",
                "dominusVelvetbot",
            )
        )
        self.assertIsNone(
            parse_reference_add_character(
                "@another_bot refadd Аид",
                "dominusVelvetbot",
            )
        )

    def test_delete_command_arguments(self) -> None:
        self.assertEqual(
            ("Темный Аид", 12),
            parse_reference_delete_args("Темный Аид #12"),
        )
        self.assertIsNone(parse_reference_delete_args("Аид"))


class ReferenceUploadSessionTests(unittest.TestCase):
    def test_session_tracks_added_references(self) -> None:
        sessions = ReferenceUploadSessions()
        sessions.start(1, character_id=7, character_name="Аид")
        updated = sessions.increment(1)
        self.assertIsNotNone(updated)
        self.assertEqual(1, updated.added_count)
        stopped = sessions.stop(1)
        self.assertEqual("Аид", stopped.character_name)


class ReferenceUiTests(unittest.TestCase):
    def setUp(self) -> None:
        character = Character(
            id=7,
            name="Аид",
            created_by=1,
            created_in_chat=2,
            created_at=datetime(2026, 7, 15, tzinfo=UTC),
            archive_chat_id=None,
            archive_thread_id=None,
            archive_topic_url=None,
        )
        reference = CharacterReference(
            id=11,
            character_id=7,
            telegram_file_id="photo-file-id",
            telegram_file_unique_id="photo-unique-id",
            added_by=1,
            created_at=datetime(2026, 7, 15, tzinfo=UTC),
        )
        self.page = ReferencePage(
            character=character,
            reference=reference,
            offset=1,
            total=3,
        )

    def test_reference_navigation_wraps(self) -> None:
        keyboard = build_reference_keyboard(self.page)
        previous = ReferenceCallback.unpack(
            keyboard.inline_keyboard[0][0].callback_data
        )
        following = ReferenceCallback.unpack(
            keyboard.inline_keyboard[0][2].callback_data
        )
        self.assertEqual(0, previous.offset)
        self.assertEqual(2, following.offset)

    def test_delete_button_targets_exact_reference(self) -> None:
        keyboard = build_reference_keyboard(self.page)
        delete_callback = ReferenceCallback.unpack(
            keyboard.inline_keyboard[1][0].callback_data
        )
        self.assertEqual("delete_prompt", delete_callback.action)
        self.assertEqual(11, delete_callback.reference_id)

    def test_delete_confirmation_has_delete_and_cancel(self) -> None:
        keyboard = build_reference_delete_keyboard(self.page)
        delete_callback = ReferenceCallback.unpack(
            keyboard.inline_keyboard[0][0].callback_data
        )
        cancel_callback = ReferenceCallback.unpack(
            keyboard.inline_keyboard[0][1].callback_data
        )
        self.assertEqual("delete", delete_callback.action)
        self.assertEqual("cancel_delete", cancel_callback.action)


if __name__ == "__main__":
    unittest.main()

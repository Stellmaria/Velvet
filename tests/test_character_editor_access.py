import unittest
from datetime import UTC, datetime

from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Chat, Message, User

from velvet_bot.access import (
    CHARACTER_EDITOR_USER_IDS,
    is_character_editor_callback,
    is_character_editor_message,
    is_character_editor_user,
)


class CharacterEditorAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.editor_id = next(iter(CHARACTER_EDITOR_USER_IDS))
        self.editor = User(
            id=self.editor_id,
            is_bot=False,
            first_name="Editor",
        )
        self.stranger = User(id=123, is_bot=False, first_name="Other")
        self.chat = Chat(id=self.editor_id, type=ChatType.PRIVATE)

    def message(self, text: str, *, user=None, reply=None) -> Message:
        return Message(
            message_id=1,
            date=datetime(2026, 7, 16, tzinfo=UTC),
            chat=self.chat,
            from_user=user or self.editor,
            text=text,
            reply_to_message=reply,
        )

    def test_editor_id_is_allowed(self) -> None:
        self.assertTrue(is_character_editor_user(self.editor))
        self.assertFalse(is_character_editor_user(self.stranger))

    def test_editor_can_open_characters_and_prompt_help(self) -> None:
        self.assertTrue(is_character_editor_message(self.message("/characters")))
        self.assertTrue(is_character_editor_message(self.message("/prompt")))
        self.assertFalse(is_character_editor_message(self.message("/create Каин")))

    def test_editor_can_reply_with_prompt_link(self) -> None:
        marker = self.message("PROMPT_MEDIA:1:2:0")
        reply = self.message(
            "https://t.me/velvetAnatomy/12",
            reply=marker,
        )
        self.assertTrue(is_character_editor_message(reply))

    def test_editor_can_use_only_directory_archive_callbacks(self) -> None:
        for data in ("adir:profile:male::0:1::0", "astory:page:male:0:1:1:0", "arc:open:1:0:0"):
            callback = CallbackQuery(
                id="callback",
                from_user=self.editor,
                chat_instance="instance",
                data=data,
            )
            with self.subTest(data=data):
                self.assertTrue(is_character_editor_callback(callback))

        forbidden = CallbackQuery(
            id="callback-2",
            from_user=self.editor,
            chat_instance="instance",
            data="other:delete",
        )
        self.assertFalse(is_character_editor_callback(forbidden))

    def test_stranger_cannot_use_directory_callback(self) -> None:
        callback = CallbackQuery(
            id="callback",
            from_user=self.stranger,
            chat_instance="instance",
            data="adir:categories::::0:0::0",
        )
        self.assertFalse(is_character_editor_callback(callback))


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import UTC, datetime

from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Chat, Message, User

from velvet_bot.access import (
    is_character_editor_callback,
    is_character_editor_message,
    is_character_editor_user,
)


EDITOR_ID = 900000001
EDITOR_IDS = frozenset({EDITOR_ID})


class CharacterEditorAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.editor = User(
  id=EDITOR_ID,
  is_bot=False,
  first_name="Editor",
        )
        self.stranger = User(id=123, is_bot=False, first_name="Other")
        self.chat = Chat(id=EDITOR_ID, type=ChatType.PRIVATE)

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
        self.assertTrue(is_character_editor_user(self.editor, EDITOR_IDS))
        self.assertFalse(is_character_editor_user(self.stranger, EDITOR_IDS))

    def test_editor_can_open_characters_and_prompt_help(self) -> None:
        self.assertTrue(
  is_character_editor_message(self.message("/characters"), EDITOR_IDS)
        )
        self.assertTrue(is_character_editor_message(self.message("/prompt"), EDITOR_IDS))
        self.assertFalse(
  is_character_editor_message(self.message("/create Каин"), EDITOR_IDS)
        )

    def test_editor_can_reply_with_prompt_link(self) -> None:
        marker = self.message("PROMPT_MEDIA:1:2:0")
        reply = self.message(
  "https://t.me/example_channel/12",
  reply=marker,
        )
        self.assertTrue(is_character_editor_message(reply, EDITOR_IDS))

    def test_editor_can_use_only_directory_archive_callbacks(self) -> None:
        for data in (
  "adir:profile:male::0:1::0",
  "astory:page:male:0:1:1:0",
  "arc:open:1:0:0",
        ):
  callback = CallbackQuery(
      id="callback",
      from_user=self.editor,
      chat_instance="instance",
      data=data,
  )
  with self.subTest(data=data):
      self.assertTrue(is_character_editor_callback(callback, EDITOR_IDS))

        forbidden = CallbackQuery(
  id="callback-2",
  from_user=self.editor,
  chat_instance="instance",
  data="other:delete",
        )
        self.assertFalse(is_character_editor_callback(forbidden, EDITOR_IDS))

    def test_stranger_cannot_use_directory_callback(self) -> None:
        callback = CallbackQuery(
  id="callback",
  from_user=self.stranger,
  chat_instance="instance",
  data="adir:categories::::0:0::0",
        )
        self.assertFalse(is_character_editor_callback(callback, EDITOR_IDS))


if __name__ == "__main__":
    unittest.main()

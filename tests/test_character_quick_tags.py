from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.character_resolution import resolve_character
from velvet_bot.core.access import (
    CHARACTER_TAG_REPLY_MARKER,
    MODERATOR_TAG_COMMANDS,
    is_moderator_callback_data,
)
from velvet_bot.presentation.telegram.middleware.access import is_moderator_message
from velvet_bot.presentation.telegram.routers.characters.aliases import CharacterTagCallback
from velvet_bot.presentation.telegram.routers.characters.directory import _profile_keyboard


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False


class CharacterQuickTagTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_character_name_wins_without_alias_query(self) -> None:
        character = SimpleNamespace(id=7, name="Макс Кроу")
        database = SimpleNamespace(
            get_character=AsyncMock(return_value=character),
            acquire=Mock(),
        )

        result = await resolve_character(database, "Макс Кроу")

        self.assertIs(result, character)
        database.acquire.assert_not_called()

    async def test_quick_tag_resolves_to_canonical_character(self) -> None:
        character = SimpleNamespace(id=7, name="Макс Кроу")
        connection = SimpleNamespace(fetchval=AsyncMock(return_value="Макс Кроу"))
        database = SimpleNamespace(
            get_character=AsyncMock(side_effect=[None, character]),
            acquire=Mock(return_value=_AsyncContext(connection)),
        )

        result = await resolve_character(database, "Кроу")

        self.assertIs(result, character)
        sql, normalized = connection.fetchval.await_args.args
        self.assertIn("FROM character_aliases AS a", sql)
        self.assertEqual(normalized, "кроу")
        self.assertEqual(database.get_character.await_args_list[1].args, ("Макс Кроу",))

    def test_character_card_contains_quick_tag_button(self) -> None:
        item = SimpleNamespace(
            character=SimpleNamespace(id=41, name="Макс Кроу"),
            category="male",
            universe="Original",
            story_id=None,
            story_short_label=None,
            story_title=None,
            media_count=3,
            prompt_post_url=None,
        )

        markup = _profile_keyboard(item, category="male", page=2)
        button = next(
            button
            for row in markup.inline_keyboard
            for button in row
            if button.text == "🏷 Быстрые теги"
        )
        data = CharacterTagCallback.unpack(button.callback_data)
        self.assertEqual(data.action, "menu")
        self.assertEqual(data.character_id, 41)
        self.assertEqual(data.category, "male")
        self.assertEqual(data.page, 2)
        self.assertLessEqual(len(button.callback_data.encode("utf-8")), 64)

    def test_moderator_access_includes_tag_commands_and_callbacks(self) -> None:
        self.assertTrue(
            {"tagadd", "tags", "tagdel"}.issubset(MODERATOR_TAG_COMMANDS)
        )
        callback_data = CharacterTagCallback(
            action="menu",
            character_id=41,
        ).pack()
        self.assertTrue(is_moderator_callback_data(callback_data))

    def test_moderator_can_answer_tag_force_reply(self) -> None:
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=44),
            guest_bot_caller_user=None,
            text="Кроу",
            caption=None,
            reply_to_message=SimpleNamespace(
                text=f"Добавьте тег\n{CHARACTER_TAG_REPLY_MARKER}41",
                caption=None,
            ),
        )
        self.assertTrue(
            is_moderator_message(message, moderator_user_ids=frozenset({44}))
        )
        self.assertFalse(
            is_moderator_message(message, moderator_user_ids=frozenset({99}))
        )


if __name__ == "__main__":
    unittest.main()

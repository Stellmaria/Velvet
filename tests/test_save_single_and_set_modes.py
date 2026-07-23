from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.app.save_sessions import SaveUploadSessions
from velvet_bot.core.access import is_workspace_member_command_text
from velvet_bot.presentation.telegram import save_mode_runtime as save_modes


def _message(
    *,
    text: str | None = None,
    chat_id: int = 10,
    user_id: int = 20,
    photo=None,
    document=None,
):
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id),
        from_user=SimpleNamespace(id=user_id),
        guest_bot_caller_user=None,
        message_id=30,
        message_thread_id=None,
        text=text,
        caption=None,
        reply_to_message=None,
        photo=photo,
        video=None,
        animation=None,
        document=document,
        answer=AsyncMock(),
    )


class SaveSessionModeTests(unittest.TestCase):
    def test_default_session_is_set_mode_for_button_compatibility(self) -> None:
        sessions = SaveUploadSessions(ttl_seconds=60, clock=lambda: 100.0)
        session = sessions.start(
            chat_id=1,
            user_id=2,
            character_name="Артур",
            command_message_id=3,
        )

        self.assertEqual("set", session.mode)

    def test_single_mode_is_stored_explicitly(self) -> None:
        sessions = SaveUploadSessions(ttl_seconds=60, clock=lambda: 100.0)
        session = sessions.start(
            chat_id=1,
            user_id=2,
            character_name="Артур",
            command_message_id=3,
            mode="single",
        )

        self.assertEqual("single", session.mode)


class SaveModeCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_without_media_selects_single_mode(self) -> None:
        result = await save_modes.SaveModeCommandFilter()(
            _message(text="/save Артур")
        )

        self.assertEqual(
            {"save_mode": "single", "save_character_name": "Артур"},
            result,
        )

    async def test_save_set_selects_batch_mode(self) -> None:
        result = await save_modes.SaveModeCommandFilter()(
            _message(text="/save_set Артур")
        )

        self.assertEqual(
            {"save_mode": "set", "save_character_name": "Артур"},
            result,
        )

    def test_workspace_access_allows_save_set(self) -> None:
        self.assertTrue(is_workspace_member_command_text("/save_set Артур"))

    def test_editor_command_menu_exposes_both_modes(self) -> None:
        commands = {
            item.command: item.description
            for item in save_modes._workspace_commands_with_save_modes("editor")
        }

        self.assertEqual("Сохранить один файл", commands["save"])
        self.assertEqual("Пакетная загрузка файлов", commands["save_set"])


class PendingSaveModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_mode_closes_after_first_supported_file(self) -> None:
        sessions = SaveUploadSessions(ttl_seconds=60, clock=lambda: 100.0)
        session = sessions.start(
            chat_id=10,
            user_id=20,
            character_name="Артур",
            command_message_id=30,
            mode="single",
        )
        message = _message(
            photo=[
                SimpleNamespace(
                    file_id="photo-id",
                    file_unique_id="photo-unique",
                    file_size=123,
                )
            ]
        )

        with patch.object(
            save_modes,
            "save_media_from_message",
            new=AsyncMock(return_value="saved"),
        ):
            await save_modes.handle_pending_save_upload(
                message,
                session,
                sessions,
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
            )

        self.assertIsNone(sessions.get(chat_id=10, user_id=20))
        self.assertIn("Одиночное сохранение завершено", message.answer.await_args.args[0])
        self.assertNotIn("Пакетная загрузка продолжается", message.answer.await_args.args[0])

    async def test_set_mode_remains_active_after_supported_file(self) -> None:
        sessions = SaveUploadSessions(ttl_seconds=60, clock=lambda: 100.0)
        session = sessions.start(
            chat_id=10,
            user_id=20,
            character_name="Артур",
            command_message_id=30,
            mode="set",
        )
        message = _message(
            photo=[
                SimpleNamespace(
                    file_id="photo-id",
                    file_unique_id="photo-unique",
                    file_size=123,
                )
            ]
        )

        with patch.object(
            save_modes,
            "save_media_from_message",
            new=AsyncMock(return_value="saved"),
        ):
            await save_modes.handle_pending_save_upload(
                message,
                session,
                sessions,
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
            )

        active = sessions.get(chat_id=10, user_id=20)
        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(1, active.saved_count)
        self.assertIn("Пакетная загрузка продолжается", message.answer.await_args.args[0])
        self.assertIsNotNone(message.answer.await_args.kwargs["reply_markup"])


if __name__ == "__main__":
    unittest.main()

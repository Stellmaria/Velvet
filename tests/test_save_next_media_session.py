from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.app.save_sessions import SaveUploadSessions
from velvet_bot.presentation.telegram.routers.archive import save as save_router


def _message(*, chat_id: int = 10, user_id: int = 20, photo=None, document=None):
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id),
        from_user=SimpleNamespace(id=user_id),
        guest_bot_caller_user=None,
        message_id=30,
        message_thread_id=None,
        reply_to_message=None,
        photo=photo,
        video=None,
        animation=None,
        document=document,
        answer=AsyncMock(),
    )


class SaveUploadSessionsTests(unittest.TestCase):
    def test_session_is_scoped_by_chat_and_user(self) -> None:
        sessions = SaveUploadSessions(ttl_seconds=60, clock=lambda: 100.0)
        created = sessions.start(
            chat_id=1,
            user_id=2,
            character_name="Артур",
            command_message_id=3,
        )

        self.assertIs(sessions.get(chat_id=1, user_id=2), created)
        self.assertIsNone(sessions.get(chat_id=1, user_id=99))
        self.assertIsNone(sessions.get(chat_id=99, user_id=2))

    def test_expired_session_is_removed(self) -> None:
        now = [100.0]
        sessions = SaveUploadSessions(ttl_seconds=10, clock=lambda: now[0])
        sessions.start(
            chat_id=1,
            user_id=2,
            character_name="Артур",
            command_message_id=3,
        )

        now[0] = 111.0

        self.assertIsNone(sessions.get(chat_id=1, user_id=2))
        self.assertIsNone(sessions.stop(chat_id=1, user_id=2))

    def test_start_replaces_previous_character_for_same_scope(self) -> None:
        sessions = SaveUploadSessions(ttl_seconds=60, clock=lambda: 100.0)
        sessions.start(
            chat_id=1,
            user_id=2,
            character_name="Артур",
            command_message_id=3,
        )
        replacement = sessions.start(
            chat_id=1,
            user_id=2,
            character_name="Кайн",
            command_message_id=4,
        )

        self.assertIs(sessions.get(chat_id=1, user_id=2), replacement)
        self.assertEqual(replacement.character_name, "Кайн")

    def test_record_saved_keeps_batch_active_and_extends_ttl(self) -> None:
        now = [100.0]
        sessions = SaveUploadSessions(ttl_seconds=10, clock=lambda: now[0])
        sessions.start(
            chat_id=1,
            user_id=2,
            character_name="Артур",
            command_message_id=3,
        )
        now[0] = 108.0

        updated = sessions.record_saved(chat_id=1, user_id=2)

        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated.saved_count, 1)
        self.assertEqual(updated.expires_at, 118.0)
        self.assertIs(sessions.get(chat_id=1, user_id=2), updated)


class SaveNextMediaHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_pending_filter_matches_only_active_scope(self) -> None:
        sessions = SaveUploadSessions(ttl_seconds=60, clock=lambda: 100.0)
        sessions.start(
            chat_id=10,
            user_id=20,
            character_name="Артур",
            command_message_id=30,
        )
        filter_ = save_router.PendingSaveUploadFilter()

        matched = await filter_(_message(), sessions)
        missing = await filter_(_message(user_id=21), sessions)

        self.assertIsInstance(matched, dict)
        self.assertEqual(matched["save_upload_session"].character_name, "Артур")
        self.assertFalse(missing)

    async def test_supported_photo_is_saved_and_batch_session_remains_active(self) -> None:
        sessions = SaveUploadSessions(ttl_seconds=60, clock=lambda: 100.0)
        session = sessions.start(
            chat_id=10,
            user_id=20,
            character_name="Артур",
            command_message_id=30,
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
            save_router,
            "save_media_from_message",
            new=AsyncMock(return_value="saved"),
        ) as save_media:
            await save_router.handle_pending_save_upload(
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
        self.assertEqual(active.saved_count, 1)
        save_media.assert_awaited_once()
        self.assertEqual(save_media.await_args.kwargs["character_name"], "Артур")
        self.assertIs(save_media.await_args.kwargs["source_message"], message)
        self.assertIn("saved", message.answer.await_args.args[0])
        self.assertIn("Пакетная загрузка продолжается", message.answer.await_args.args[0])
        self.assertIsNotNone(message.answer.await_args.kwargs["reply_markup"])

    async def test_unsupported_document_keeps_session_active(self) -> None:
        sessions = SaveUploadSessions(ttl_seconds=60, clock=lambda: 100.0)
        session = sessions.start(
            chat_id=10,
            user_id=20,
            character_name="Артур",
            command_message_id=30,
        )
        message = _message(
            document=SimpleNamespace(
                file_id="pdf-id",
                file_unique_id="pdf-unique",
                file_name="notes.pdf",
                mime_type="application/pdf",
                file_size=456,
                thumbnail=None,
            )
        )

        with patch.object(
            save_router,
            "save_media_from_message",
            new=AsyncMock(),
        ) as save_media:
            await save_router.handle_pending_save_upload(
                message,
                session,
                sessions,
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(),
            )

        self.assertIs(sessions.get(chat_id=10, user_id=20), session)
        save_media.assert_not_awaited()
        self.assertIn("не поддерживается", message.answer.await_args.args[0])

    async def test_start_session_resolves_alias_to_canonical_name(self) -> None:
        sessions = SaveUploadSessions(ttl_seconds=60, clock=lambda: 100.0)
        message = _message()

        with patch.object(
            save_router,
            "resolve_character",
            new=AsyncMock(return_value=SimpleNamespace(name="Артур Пендрагон")),
        ):
            await save_router._start_save_session(
                message,
                "Артур",
                SimpleNamespace(),
                sessions,
            )

        session = sessions.get(chat_id=10, user_id=20)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.character_name, "Артур Пендрагон")
        self.assertIn("Артур Пендрагон", message.answer.await_args.args[0])

    async def test_savecancel_removes_active_session(self) -> None:
        sessions = SaveUploadSessions(ttl_seconds=60, clock=lambda: 100.0)
        sessions.start(
            chat_id=10,
            user_id=20,
            character_name="Артур",
            command_message_id=30,
        )
        message = _message()

        await save_router.handle_save_cancel(message, sessions)

        self.assertIsNone(sessions.get(chat_id=10, user_id=20))
        self.assertIn("файлы не были добавлены", message.answer.await_args.args[0])

    def test_personal_batch_keyboard_exposes_all_exit_paths(self) -> None:
        keyboard = save_router._batch_save_keyboard(
            workspace_id=5,
            character_id=7,
        )
        labels = [
            button.text
            for row in keyboard.inline_keyboard
            for button in row
        ]

        self.assertEqual(
            [
                "✅ Закончить загрузку",
                "↩️ Открыть карточку",
                "👤 Другой персонаж",
                "✖ Отменить режим",
            ],
            labels,
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.handlers.guest_archive as module


class FakeAudit:
    def __init__(self) -> None:
        self.errors: list[tuple[str, BaseException, dict[str, object]]] = []
        self.sends: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def error(self, title: str, error: BaseException, **fields) -> None:
        self.errors.append((title, error, fields))

    async def send(self, *args, **kwargs) -> None:
        self.sends.append((args, kwargs))


class FakeDatabase:
    def __init__(
        self,
        *,
        character=None,
        get_error: BaseException | None = None,
        save_result=None,
    ) -> None:
        self.character = character
        self.get_error = get_error
        self.save_result = save_result
        self.archive_updates: list[tuple[int, int, int]] = []

    async def get_character(self, name: str):
        if self.get_error is not None:
            raise self.get_error
        return self.character

    async def save_character_media(self, *args, **kwargs):
        return self.save_result

    async def set_archive_message_id(
        self,
        character_id: int,
        media_id: int,
        archive_message_id: int,
    ) -> None:
        self.archive_updates.append((character_id, media_id, archive_message_id))


class GuestArchiveBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_parse = module.parse_guest_save_character
        self.original_resolve = module._resolve_guest_source
        self.original_extract = module.extract_media
        self.original_answer = module._send_guest_answer
        self.original_send_media = module.send_media_to_topic

        self.source = module.GuestSource(
            media_source=object(),
            source_chat_id=-200,
            source_message_id=55,
            source_thread_id=9,
        )
        self.media = SimpleNamespace(media_type="photo")
        self.message = SimpleNamespace(
            guest_query_id="query-1",
            from_user=SimpleNamespace(id=17, username="owner"),
            guest_bot_caller_user=None,
            reply_to_message=None,
            external_reply=None,
            text="@velvet save Ada",
            caption=None,
            chat=SimpleNamespace(id=-100),
            message_id=77,
        )
        self.answers: list[str] = []

        module.parse_guest_save_character = lambda text, bot_username: "Ada"
        module._resolve_guest_source = lambda message: self.source
        module.extract_media = lambda source: self.media

        async def record_answer(message, text: str) -> None:
            self.answers.append(text)

        module._send_guest_answer = record_answer

    def tearDown(self) -> None:
        module.parse_guest_save_character = self.original_parse
        module._resolve_guest_source = self.original_resolve
        module.extract_media = self.original_extract
        module._send_guest_answer = self.original_answer
        module.send_media_to_topic = self.original_send_media

    async def test_general_failure_is_audited_once_and_answered(self) -> None:
        error = RuntimeError("database unavailable")
        database = FakeDatabase(get_error=error)
        audit = FakeAudit()

        await module.handle_guest_archive(
            self.message,
            database,
            object(),
            "velvet",
            audit,
        )

        self.assertEqual(len(audit.errors), 1)
        title, recorded_error, fields = audit.errors[0]
        self.assertEqual(title, "Ошибка Guest Mode")
        self.assertIs(recorded_error, error)
        self.assertEqual(fields["character"], "Ada")
        self.assertEqual(fields["caller_id"], 17)
        self.assertEqual(fields["source_chat_id"], -200)
        self.assertEqual(fields["source_message_id"], 55)
        self.assertEqual(len(self.answers), 1)
        self.assertIn("database unavailable", self.answers[0])

    async def test_topic_delivery_failure_is_not_audited_twice(self) -> None:
        error = RuntimeError("topic unavailable")
        character = SimpleNamespace(
            id=7,
            name="Ada",
            archive_chat_id=-300,
            archive_thread_id=12,
        )
        result = SimpleNamespace(
            character_link_created=False,
            storage_file_name="ada-photo.jpg",
            archive_message_id=None,
            media_id=5,
            media_created=False,
        )
        database = FakeDatabase(character=character, save_result=result)
        audit = FakeAudit()

        async def fail_delivery(*args, **kwargs):
            raise error

        module.send_media_to_topic = fail_delivery

        await module.handle_guest_archive(
            self.message,
            database,
            object(),
            "velvet",
            audit,
        )

        self.assertEqual(len(audit.errors), 1)
        title, recorded_error, fields = audit.errors[0]
        self.assertEqual(title, "Ошибка отправки Guest-медиа в ветку")
        self.assertIs(recorded_error, error)
        self.assertEqual(fields["character"], "Ada")
        self.assertEqual(fields["file"], "ada-photo.jpg")
        self.assertEqual(fields["archive_chat_id"], -300)
        self.assertEqual(fields["archive_thread_id"], 12)
        self.assertEqual(len(self.answers), 1)
        self.assertIn("topic unavailable", self.answers[0])

    async def test_topic_delivery_cancellation_is_not_swallowed(self) -> None:
        character = SimpleNamespace(
            id=7,
            name="Ada",
            archive_chat_id=-300,
            archive_thread_id=12,
        )
        result = SimpleNamespace(
            character_link_created=False,
            storage_file_name="ada-photo.jpg",
            archive_message_id=None,
            media_id=5,
            media_created=False,
        )
        database = FakeDatabase(character=character, save_result=result)
        audit = FakeAudit()

        async def cancel_delivery(*args, **kwargs):
            raise asyncio.CancelledError

        module.send_media_to_topic = cancel_delivery

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_guest_archive(
                self.message,
                database,
                object(),
                "velvet",
                audit,
            )

        self.assertEqual(audit.errors, [])
        self.assertEqual(self.answers, [])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.handlers.archive as module


class FakeBot:
    async def get_me(self):
        return SimpleNamespace(id=999)


class FakeDatabase:
    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.character = SimpleNamespace(id=7, name="Ada")
        self.save_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def get_character_by_archive_topic(self, chat_id: int, thread_id: int):
        return self.character

    async def save_character_media(self, *args, **kwargs):
        self.save_calls.append((args, kwargs))
        raise self.error


class FakeAudit:
    def __init__(self) -> None:
        self.errors: list[tuple[str, BaseException, dict[str, object]]] = []

    async def error(self, title: str, error: BaseException, **fields) -> None:
        self.errors.append((title, error, fields))

    async def send(self, *args, **kwargs) -> None:
        raise AssertionError("success audit must not be sent after save failure")


class TopicArchiveBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_extract_media = module.extract_media
        module.extract_media = lambda message: SimpleNamespace(media_type="photo")
        self.message = SimpleNamespace(
            message_thread_id=23,
            from_user=SimpleNamespace(id=11),
            chat=SimpleNamespace(id=-1001),
            message_id=77,
        )

    def tearDown(self) -> None:
        module.extract_media = self.original_extract_media

    async def test_save_failure_is_reported_to_audit(self) -> None:
        error = RuntimeError("database unavailable")
        database = FakeDatabase(error)
        audit = FakeAudit()

        await module.handle_new_archive_topic_media(
            self.message,
            database,
            FakeBot(),
            audit,
        )

        self.assertEqual(len(database.save_calls), 1)
        _, save_fields = database.save_calls[0]
        self.assertEqual(save_fields["saved_by"], 11)
        self.assertEqual(save_fields["saved_in_chat"], -1001)
        self.assertEqual(save_fields["source_chat_id"], -1001)
        self.assertEqual(save_fields["source_message_id"], 77)
        self.assertEqual(save_fields["source_thread_id"], 23)
        self.assertEqual(save_fields["archive_message_id"], 77)

        self.assertEqual(len(audit.errors), 1)
        title, recorded_error, fields = audit.errors[0]
        self.assertEqual(title, "Ошибка автоматического архива общей ветки")
        self.assertIs(recorded_error, error)
        self.assertEqual(fields["character"], "Ada")
        self.assertEqual(fields["archive_chat_id"], -1001)
        self.assertEqual(fields["archive_thread_id"], 23)
        self.assertEqual(fields["archive_message_id"], 77)

    async def test_cancellation_is_not_converted_to_audit_error(self) -> None:
        database = FakeDatabase(asyncio.CancelledError())
        audit = FakeAudit()

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_new_archive_topic_media(
                self.message,
                database,
                FakeBot(),
                audit,
            )

        self.assertEqual(len(database.save_calls), 1)
        self.assertEqual(audit.errors, [])


if __name__ == "__main__":
    unittest.main()

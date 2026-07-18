from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.services.media_save as module


class FakeAuditLogger:
    def __init__(self) -> None:
        self.errors: list[tuple[str, BaseException, dict[str, object]]] = []
        self.messages: list[tuple[str, dict[str, object]]] = []

    async def error(self, title: str, error: BaseException, **fields) -> None:
        self.errors.append((title, error, fields))

    async def send(self, title: str, **fields) -> None:
        self.messages.append((title, fields))


class FakeDatabase:
    def __init__(self) -> None:
        self.archive_calls: list[tuple[int, int, int]] = []

    async def set_archive_message_id(
        self,
        character_id: int,
        media_id: int,
        message_id: int,
    ) -> None:
        self.archive_calls.append((character_id, media_id, message_id))


class MediaSaveBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_save = module._save_media_from_message
        self.original_send_topic = module.send_media_to_topic

        self.request = SimpleNamespace(
            chat=SimpleNamespace(id=23),
            message_id=31,
        )
        self.source = SimpleNamespace(
            chat=SimpleNamespace(id=99),
            message_id=41,
            message_thread_id=None,
        )
        self.character = SimpleNamespace(
            id=7,
            name='Ada',
            archive_chat_id=77,
            archive_thread_id=88,
        )
        self.media = SimpleNamespace(
            storage_file_name='ada-image.png',
            media_type='document',
        )
        self.result = SimpleNamespace(
            media_id=11,
            archive_message_id=None,
        )

    def tearDown(self) -> None:
        module._save_media_from_message = self.original_save
        module.send_media_to_topic = self.original_send_topic

    async def test_outer_failure_is_audited_and_returns_safe_message(self) -> None:
        error = RuntimeError('database write failed')

        async def fail_save(*args, **kwargs):
            raise error

        module._save_media_from_message = fail_save
        audit = FakeAuditLogger()

        with self.assertLogs(module.logger, level='ERROR') as captured:
            result = await module.save_media_from_message(
                object(),
                object(),
                audit,
                request_message=self.request,
                source_message=self.source,
                character_name='Ada',
                actor_id=17,
            )

        self.assertEqual(
            result,
            'Не удалось сохранить медиафайл из-за внутренней ошибки.',
        )
        self.assertEqual(len(audit.errors), 1)
        title, captured_error, fields = audit.errors[0]
        self.assertEqual(title, 'Ошибка сохранения медиа')
        self.assertIs(captured_error, error)
        self.assertEqual(
            fields,
            {
                'character': 'Ada',
                'chat_id': 23,
                'message_id': 31,
                'user_id': 17,
            },
        )
        self.assertIn('database write failed', '\n'.join(captured.output))

    async def test_outer_cancellation_is_not_audited_or_swallowed(self) -> None:
        async def cancel_save(*args, **kwargs):
            raise asyncio.CancelledError

        module._save_media_from_message = cancel_save
        audit = FakeAuditLogger()

        with self.assertRaises(asyncio.CancelledError):
            await module.save_media_from_message(
                object(),
                object(),
                audit,
                request_message=self.request,
                source_message=self.source,
                character_name='Ada',
                actor_id=17,
            )

        self.assertEqual(audit.errors, [])

    async def test_topic_failure_is_audited_and_returns_partial_result(self) -> None:
        error = RuntimeError('topic unavailable')

        async def fail_topic(*args, **kwargs):
            raise error

        module.send_media_to_topic = fail_topic
        database = FakeDatabase()
        audit = FakeAuditLogger()

        with self.assertLogs(module.logger, level='ERROR') as captured:
            uploaded, reason = await module._place_in_topic(
                object(),
                database,
                audit,
                character=self.character,
                media=self.media,
                source_message=self.source,
                result=self.result,
            )

        self.assertFalse(uploaded)
        self.assertEqual(reason, 'topic unavailable')
        self.assertEqual(database.archive_calls, [])
        self.assertEqual(len(audit.errors), 1)
        title, captured_error, fields = audit.errors[0]
        self.assertEqual(title, 'Ошибка отправки медиа в ветку')
        self.assertIs(captured_error, error)
        self.assertEqual(fields['character'], 'Ada')
        self.assertEqual(fields['file'], 'ada-image.png')
        self.assertEqual(fields['archive_chat_id'], 77)
        self.assertEqual(fields['archive_thread_id'], 88)
        self.assertIn('topic unavailable', '\n'.join(captured.output))

    async def test_topic_cancellation_is_not_audited_or_swallowed(self) -> None:
        async def cancel_topic(*args, **kwargs):
            raise asyncio.CancelledError

        module.send_media_to_topic = cancel_topic
        audit = FakeAuditLogger()

        with self.assertRaises(asyncio.CancelledError):
            await module._place_in_topic(
                object(),
                FakeDatabase(),
                audit,
                character=self.character,
                media=self.media,
                source_message=self.source,
                result=self.result,
            )

        self.assertEqual(audit.errors, [])

    async def test_topic_success_persists_message_and_audits_success(self) -> None:
        async def send_topic(*args, **kwargs):
            return SimpleNamespace(message_id=333)

        module.send_media_to_topic = send_topic
        database = FakeDatabase()
        audit = FakeAuditLogger()

        uploaded, reason = await module._place_in_topic(
            object(),
            database,
            audit,
            character=self.character,
            media=self.media,
            source_message=self.source,
            result=self.result,
        )

        self.assertTrue(uploaded)
        self.assertIsNone(reason)
        self.assertEqual(database.archive_calls, [(7, 11, 333)])
        self.assertEqual(len(audit.messages), 1)
        title, fields = audit.messages[0]
        self.assertEqual(title, 'Медиа отправлено в ветку')
        self.assertEqual(fields['archive_message_id'], 333)
        self.assertEqual(fields['level'], 'SUCCESS')


if __name__ == '__main__':
    unittest.main()

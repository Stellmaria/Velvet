from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.handlers.reference_comparison as module


class FakeStatus:
    def __init__(self) -> None:
        self.edits: list[str] = []

    async def edit_text(self, text: str, **kwargs) -> None:
        self.edits.append(text)


class FakeMessage:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(type=module.ChatType.PRIVATE, id=23)
        self.from_user = SimpleNamespace(id=17)
        self.message_id = 31
        self.status = FakeStatus()
        self.answers: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))
        return self.status


class FakeAuditLogger:
    def __init__(self) -> None:
        self.errors: list[tuple[str, BaseException, dict[str, object]]] = []

    async def error(self, title: str, error: BaseException, **fields) -> None:
        self.errors.append((title, error, fields))


class ReferenceComparisonAuditTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_result_file = module._result_file
        self.original_resolve_reference = module._resolve_reference
        self.original_settings = module.load_settings
        self.original_download = module._download_file

        self.character = SimpleNamespace(id=7, name='Ada')
        self.reference = SimpleNamespace(id=11, telegram_file_id='reference-file')
        module._result_file = lambda message: ('result-file', 'result-unique')

        async def resolve_reference(database, raw_value):
            return self.character, self.reference, 1, 1

        module._resolve_reference = resolve_reference
        module.load_settings = lambda: SimpleNamespace(ai_vision_enabled=True)

    def tearDown(self) -> None:
        module._result_file = self.original_result_file
        module._resolve_reference = self.original_resolve_reference
        module.load_settings = self.original_settings
        module._download_file = self.original_download

    async def test_failure_is_audited_with_reference_context_and_reported(self) -> None:
        error = RuntimeError('comparison failed')

        async def fail_download(bot, file_id):
            raise error

        module._download_file = fail_download
        message = FakeMessage()
        audit = FakeAuditLogger()

        await module.handle_reference_comparison(
            message,
            SimpleNamespace(args='Ada 1'),
            object(),
            object(),
            audit,
        )

        self.assertEqual(len(audit.errors), 1)
        title, captured, fields = audit.errors[0]
        self.assertEqual(title, 'Ошибка сравнения с референсом')
        self.assertIs(captured, error)
        self.assertEqual(
            fields,
            {
                'character_id': 7,
                'reference_id': 11,
                'result_file_id': 'result-file',
                'result_file_unique_id': 'result-unique',
                'user_id': 17,
            },
        )
        self.assertEqual(len(message.status.edits), 1)
        self.assertIn('Ошибка отправлена в центр инцидентов', message.status.edits[0])
        self.assertIn('comparison failed', message.status.edits[0])

    async def test_failure_without_audit_logger_still_updates_status(self) -> None:
        async def fail_download(bot, file_id):
            raise RuntimeError('offline')

        module._download_file = fail_download
        message = FakeMessage()

        await module.handle_reference_comparison(
            message,
            SimpleNamespace(args='Ada'),
            object(),
            object(),
        )

        self.assertEqual(len(message.status.edits), 1)
        self.assertIn('offline', message.status.edits[0])

    async def test_cancellation_is_not_audited_or_reported_as_failure(self) -> None:
        async def cancel_download(bot, file_id):
            raise asyncio.CancelledError

        module._download_file = cancel_download
        message = FakeMessage()
        audit = FakeAuditLogger()

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_reference_comparison(
                message,
                SimpleNamespace(args='Ada'),
                object(),
                object(),
                audit,
            )

        self.assertEqual(audit.errors, [])
        self.assertEqual(message.status.edits, [])


if __name__ == '__main__':
    unittest.main()

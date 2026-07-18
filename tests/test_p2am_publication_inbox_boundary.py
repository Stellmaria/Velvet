from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.publication_inbox_middleware as module


class FakeMessage:
    def __init__(self, *, reply_text: str = '') -> None:
        self.chat = SimpleNamespace(type=module.ChatType.PRIVATE, id=23)
        self.from_user = SimpleNamespace(id=17)
        self.message_id = 31
        self.text = 'publication draft'
        self.caption = None
        self.reply_to_message = (
            SimpleNamespace(text=reply_text, caption=None)
            if reply_text
            else None
        )


class FakeAccessPolicy:
    def allows_user(self, user) -> bool:
        return True


class FakeDatabase:
    pass


class PublicationInboxBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_message = module.Message
        self.original_policy = module.AccessPolicy
        self.original_database = module.Database
        self.original_capture = module.capture_publication_inbox
        module.Message = FakeMessage
        module.AccessPolicy = FakeAccessPolicy
        module.Database = FakeDatabase

    def tearDown(self) -> None:
        module.Message = self.original_message
        module.AccessPolicy = self.original_policy
        module.Database = self.original_database
        module.capture_publication_inbox = self.original_capture

    async def test_capture_failure_is_logged_and_handler_still_runs(self) -> None:
        error = RuntimeError('capture write failed')
        capture_calls: list[dict[str, object]] = []
        handler_calls: list[object] = []

        async def fail_capture(database, message, **kwargs):
            capture_calls.append({'database': database, 'message': message, **kwargs})
            raise error

        async def handler(event, data):
            handler_calls.append(event)
            return 'handled'

        module.capture_publication_inbox = fail_capture
        message = FakeMessage()
        database = FakeDatabase()
        data = {'access_policy': FakeAccessPolicy(), 'database': database}

        with self.assertLogs(module.logger, level='ERROR') as captured:
            result = await module.PublicationInboxMiddleware()(handler, message, data)

        self.assertEqual(result, 'handled')
        self.assertEqual(len(capture_calls), 1)
        self.assertIs(capture_calls[0]['database'], database)
        self.assertEqual(capture_calls[0]['owner_id'], 17)
        self.assertEqual(handler_calls, [message])
        rendered = '\n'.join(captured.output)
        self.assertIn('chat=23', rendered)
        self.assertIn('message=31', rendered)
        self.assertIn('capture write failed', rendered)

    async def test_capture_cancellation_stops_pipeline(self) -> None:
        handler_calls: list[object] = []

        async def cancel_capture(database, message, **kwargs):
            raise asyncio.CancelledError

        async def handler(event, data):
            handler_calls.append(event)

        module.capture_publication_inbox = cancel_capture

        with self.assertRaises(asyncio.CancelledError):
            await module.PublicationInboxMiddleware()(
                handler,
                FakeMessage(),
                {'access_policy': FakeAccessPolicy(), 'database': FakeDatabase()},
            )

        self.assertEqual(handler_calls, [])

    async def test_form_marker_skips_capture_but_runs_handler(self) -> None:
        capture_calls: list[object] = []

        async def capture(database, message, **kwargs):
            capture_calls.append(message)

        async def handler(event, data):
            return 'handled'

        module.capture_publication_inbox = capture
        result = await module.PublicationInboxMiddleware()(
            handler,
            FakeMessage(reply_text='PUBLICATION_TEXT:42'),
            {'access_policy': FakeAccessPolicy(), 'database': FakeDatabase()},
        )

        self.assertEqual(result, 'handled')
        self.assertEqual(capture_calls, [])


if __name__ == '__main__':
    unittest.main()

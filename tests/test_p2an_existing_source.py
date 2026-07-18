from __future__ import annotations

import unittest
from types import SimpleNamespace

import velvet_bot.services.media_save as module


class FakeDatabase:
    def __init__(self) -> None:
        self.calls = []

    async def set_archive_message_id(self, character_id, media_id, message_id):
        self.calls.append((character_id, media_id, message_id))


class FakeAudit:
    async def send(self, *args, **kwargs):
        raise AssertionError('unexpected send')

    async def error(self, *args, **kwargs):
        raise AssertionError('unexpected error')


class ExistingSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_source_is_linked_without_resend(self) -> None:
        original = module.send_media_to_topic

        async def unexpected(*args, **kwargs):
            raise AssertionError('unexpected resend')

        module.send_media_to_topic = unexpected
        database = FakeDatabase()
        try:
            uploaded, reason = await module._place_in_topic(
                object(),
                database,
                FakeAudit(),
                character=SimpleNamespace(
                    id=7,
                    name='Ada',
                    archive_chat_id=77,
                    archive_thread_id=88,
                ),
                media=SimpleNamespace(),
                source_message=SimpleNamespace(
                    chat=SimpleNamespace(id=77),
                    message_id=333,
                    message_thread_id=88,
                ),
                result=SimpleNamespace(media_id=11, archive_message_id=None),
            )
        finally:
            module.send_media_to_topic = original

        self.assertFalse(uploaded)
        self.assertIsNone(reason)
        self.assertEqual(database.calls, [(7, 11, 333)])


if __name__ == '__main__':
    unittest.main()

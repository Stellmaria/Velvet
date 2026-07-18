from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

import velvet_bot.handlers.characters as module


class FakeMessage:
    def __init__(self) -> None:
        self.from_user = SimpleNamespace(id=17)
        self.chat = SimpleNamespace(id=-1001)
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs) -> None:
        self.answers.append(text)


class CharacterTopicBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_create = module.create_character_profile
        self.original_bind = module.bind_character_topic

    def tearDown(self) -> None:
        module.create_character_profile = self.original_create
        module.bind_character_topic = self.original_bind

    async def test_create_failure_is_logged_and_answered(self) -> None:
        message = FakeMessage()

        async def fail_create(*args, **kwargs):
            raise RuntimeError("topic lookup unavailable")

        module.create_character_profile = fail_create

        with self.assertLogs(module.logger.name, level="ERROR") as captured:
            await module.handle_create_character(
                message,
                SimpleNamespace(args="Ada https://t.me/c/1/2"),
                object(),
                object(),
            )

        self.assertEqual(len(message.answers), 1)
        self.assertIn("topic lookup unavailable", message.answers[0])
        self.assertTrue(any("create character profile" in line for line in captured.output))

    async def test_bind_failure_is_logged_and_answered(self) -> None:
        message = FakeMessage()

        async def fail_bind(*args, **kwargs):
            raise RuntimeError("topic access unavailable")

        module.bind_character_topic = fail_bind

        with self.assertLogs(module.logger.name, level="ERROR") as captured:
            await module.handle_bind_character_topic(
                message,
                SimpleNamespace(args="Ada https://t.me/c/1/2"),
                object(),
                object(),
            )

        self.assertEqual(len(message.answers), 1)
        self.assertIn("topic access unavailable", message.answers[0])
        self.assertTrue(any("bind character topic" in line for line in captured.output))

    async def test_create_cancellation_is_not_answered(self) -> None:
        message = FakeMessage()

        async def cancel_create(*args, **kwargs):
            raise asyncio.CancelledError

        module.create_character_profile = cancel_create

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_create_character(
                message,
                SimpleNamespace(args="Ada"),
                object(),
                object(),
            )

        self.assertEqual(message.answers, [])

    async def test_bind_cancellation_is_not_answered(self) -> None:
        message = FakeMessage()

        async def cancel_bind(*args, **kwargs):
            raise asyncio.CancelledError

        module.bind_character_topic = cancel_bind

        with self.assertRaises(asyncio.CancelledError):
            await module.handle_bind_character_topic(
                message,
                SimpleNamespace(args="Ada https://t.me/c/1/2"),
                object(),
                object(),
            )

        self.assertEqual(message.answers, [])


if __name__ == "__main__":
    unittest.main()

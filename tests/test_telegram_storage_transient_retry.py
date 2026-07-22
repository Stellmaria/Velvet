from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.domains.telegram_storage.uploader import TelegramStorageUploader


class _FakeTransientTelegramError(Exception):
    pass


class _TransientOnceBot:
    def __init__(self) -> None:
        self._failed = False
        self.send_document = AsyncMock(side_effect=self._send)

    async def _send(self, **kwargs):
        del kwargs
        if not self._failed:
            self._failed = True
            raise _FakeTransientTelegramError("Request timeout error")
        return SimpleNamespace(message_id=1)


class TelegramStorageTransientRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_send_failure_retries_same_document(self) -> None:
        bot = _TransientOnceBot()
        uploader = TelegramStorageUploader(
            bot=bot,
            repository=SimpleNamespace(),
            settings=SimpleNamespace(),
        )
        sleep = AsyncMock()

        with patch(
            "velvet_bot.domains.telegram_storage.uploader.TelegramNetworkError",
            _FakeTransientTelegramError,
        ), patch(
            "velvet_bot.domains.telegram_storage.uploader.TelegramServerError",
            _FakeTransientTelegramError,
        ), patch(
            "velvet_bot.domains.telegram_storage.uploader.asyncio.sleep",
            new=sleep,
        ):
            result = await uploader._send_document(
                chat_id=-1004459280894,
                document=object(),
            )

        self.assertEqual(1, result.message_id)
        self.assertEqual(2, bot.send_document.await_count)
        sleep.assert_awaited_once_with(2.0)


if __name__ == "__main__":
    unittest.main()

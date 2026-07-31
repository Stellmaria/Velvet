from __future__ import annotations

import unittest
from uuid import uuid4

from velvet_bot.infrastructure.media_delivery_repository_record import (
    MediaDeliveryRepositoryRecordMixin,
)


class _AsyncContext:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback
        return False


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def transaction(self) -> _AsyncContext:
        return _AsyncContext(self)

    async def execute(self, query: str, *args: object) -> str:
        self.calls.append((query, args))
        return "INSERT 0 1"


class _Database:
    def __init__(self) -> None:
        self.connection = _Connection()

    def acquire(self) -> _AsyncContext:
        return _AsyncContext(self.connection)


class MediaDeliveryRepositoryRecordTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_submission_normalizes_media_kind_without_shadowing(self) -> None:
        database = _Database()
        repository = MediaDeliveryRepositoryRecordMixin(database)

        await repository.record_provider_submission(
            task_id=uuid4(),
            provider="kie",
            provider_task_id="provider-task",
            chat_id=17,
            media_kind="VIDEO",
            request={"model": "wan_26_image_to_video"},
        )

        self.assertEqual("video", database.connection.calls[0][1][4])

    async def test_provider_success_normalizes_media_kind_without_shadowing(self) -> None:
        database = _Database()
        repository = MediaDeliveryRepositoryRecordMixin(database)

        await repository.record_provider_success(
            task_id=uuid4(),
            provider="kie",
            provider_task_id="provider-task",
            chat_id=19,
            media_kind="unexpected-kind",
            request={"model": "qwen2_image_edit"},
            result_urls=("https://example.invalid/result.png", ""),
        )

        self.assertEqual("image", database.connection.calls[0][1][4])
        self.assertEqual("https://example.invalid/result.png", database.connection.calls[1][1][2])


if __name__ == "__main__":
    unittest.main()

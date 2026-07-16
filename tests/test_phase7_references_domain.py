from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.types import PhotoSize

from velvet_bot.app.reference_sessions import ReferenceUploadSessions
from velvet_bot.domains.references import ReferenceMediaPayload, ReferenceService
from velvet_bot.infrastructure.telegram import reference_payload_from_photo


class ReferenceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_rejects_missing_file_id(self) -> None:
        repository = SimpleNamespace(add=AsyncMock())
        service = ReferenceService(repository)

        with self.assertRaisesRegex(ValueError, "file_id"):
            await service.add(
                character_id=5,
                media=ReferenceMediaPayload("", "unique"),
                added_by=10,
            )

        repository.add.assert_not_awaited()

    async def test_delete_is_delegated(self) -> None:
        repository = SimpleNamespace(delete=AsyncMock(return_value="deleted"))
        service = ReferenceService(repository)

        result = await service.delete(character_id=5, reference_id=7)

        self.assertEqual(result, "deleted")
        repository.delete.assert_awaited_once_with(
            character_id=5,
            reference_id=7,
        )


class ReferenceUploadSessionTests(unittest.TestCase):
    def test_session_lifecycle_is_application_owned(self) -> None:
        sessions = ReferenceUploadSessions()
        started = sessions.start(
            10,
            character_id=5,
            character_name="Каин",
        )
        self.assertEqual(started.added_count, 0)
        self.assertEqual(sessions.increment(10).added_count, 1)
        stopped = sessions.stop(10)
        self.assertEqual(stopped.character_name, "Каин")
        self.assertIsNone(sessions.get(10))


class TelegramReferenceAdapterTests(unittest.TestCase):
    def test_photo_size_becomes_neutral_payload(self) -> None:
        photo = PhotoSize(
            file_id="file-id",
            file_unique_id="unique-id",
            width=1024,
            height=1024,
        )

        payload = reference_payload_from_photo(photo)

        self.assertEqual(payload.telegram_file_id, "file-id")
        self.assertEqual(payload.telegram_file_unique_id, "unique-id")


if __name__ == "__main__":
    unittest.main()

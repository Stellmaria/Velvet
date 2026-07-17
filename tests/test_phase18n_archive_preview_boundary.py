from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.domains.archive.preview_models import PreviewPayload
from velvet_bot.domains.archive.preview_repository import ArchivePreviewRepository


ROOT = Path(__file__).resolve().parents[1]


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self.value

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        self.exited = True
        return False


class ArchivePreviewBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary(self) -> None:
        path = ROOT / "velvet_bot/domains/archive/preview_repository.py"
        source = path.read_text(encoding="utf-8")

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("self._database.acquire()"), 2)

    async def test_load_uses_public_acquire_and_preserves_mapping(self) -> None:
        row = {
            "preview_file_id": "preview-file",
            "preview_file_unique_id": "preview-unique",
            "preview_width": 720,
            "preview_height": 1280,
            "preview_source": "generated",
            "source_chat_id": -1001,
            "source_message_id": 22,
            "archive_chat_id": -1002,
            "archive_message_id": 33,
        }
        connection = SimpleNamespace(fetchrow=AsyncMock(return_value=row))
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = ArchivePreviewRepository(database)

        result = await repository.load(character_id=7, media_id=11)

        database.acquire.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        connection.fetchrow.assert_awaited_once()
        sql, character_id, media_id = connection.fetchrow.await_args.args
        self.assertIn("FROM media_files AS mf", sql)
        self.assertIn("JOIN character_media AS cm", sql)
        self.assertEqual((character_id, media_id), (7, 11))
        self.assertEqual(result.file_id, "preview-file")
        self.assertEqual(result.file_unique_id, "preview-unique")
        self.assertEqual(result.width, 720)
        self.assertEqual(result.height, 1280)
        self.assertEqual(result.source, "generated")
        self.assertEqual(result.source_chat_id, -1001)
        self.assertEqual(result.source_message_id, 22)
        self.assertEqual(result.archive_chat_id, -1002)
        self.assertEqual(result.archive_message_id, 33)

    async def test_save_uses_public_acquire_and_preserves_arguments(self) -> None:
        connection = SimpleNamespace(execute=AsyncMock(return_value="UPDATE 1"))
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = ArchivePreviewRepository(database)
        preview = PreviewPayload(
            file_id="preview-file",
            file_unique_id="preview-unique",
            width=720,
            height=1280,
            source="generated",
        )

        await repository.save(media_id=11, preview=preview)

        database.acquire.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        connection.execute.assert_awaited_once()
        sql, *arguments = connection.execute.await_args.args
        self.assertIn("UPDATE media_files", sql)
        self.assertIn("preview_updated_at = NOW()", sql)
        self.assertEqual(
            arguments,
            [11, "preview-file", "preview-unique", 720, 1280, "generated"],
        )


if __name__ == "__main__":
    unittest.main()

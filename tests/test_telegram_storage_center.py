from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.domains.telegram_storage.files import (
    decrypt_file,
    encrypt_file,
    sha256_file,
    split_file,
    storage_message_link,
)
from velvet_bot.domains.telegram_storage.models import (
    StorageCandidate,
    StoredObject,
    TelegramStorageSettings,
)
from velvet_bot.domains.telegram_storage.uploader import TelegramStorageUploader


class TelegramStorageSettingsTests(unittest.TestCase):
    def test_real_forum_thread_mapping_is_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "SUPERVISOR_PROJECT_DIR": directory,
                "STORAGE_ENCRYPTION_SECRET": "x" * 32,
            },
            clear=False,
        ):
            settings = TelegramStorageSettings.from_env()
        self.assertEqual(-1004459280894, settings.chat_id)
        self.assertEqual(3, settings.threads.watermarks)
        self.assertEqual(4, settings.threads.backups)
        self.assertEqual(9, settings.threads.diagnostics)
        self.assertEqual(11, settings.threads.exports)
        self.assertEqual(7, settings.threads.codex)
        self.assertEqual(13, settings.threads.releases)
        self.assertEqual(15, settings.threads.rework)
        self.assertTrue(settings.migrate_on_start)
        self.assertTrue(settings.delete_after_upload)

    def test_storage_message_link_uses_internal_chat_id(self) -> None:
        self.assertEqual(
            "https://t.me/c/4459280894/77",
            storage_message_link(-1004459280894, 77),
        )


class TelegramStorageEncryptionTests(unittest.TestCase):
    def test_aes_gcm_round_trip_preserves_backup_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "backup.dump"
            encrypted = root / "backup.velvet.enc"
            restored = root / "restored.dump"
            source.write_bytes((b"velvet-backup\x00" * 10000) + os.urandom(8192))

            encrypt_file(source, encrypted, "s" * 32)
            decrypt_file(encrypted, restored, "s" * 32)

            self.assertNotEqual(source.read_bytes(), encrypted.read_bytes())
            self.assertEqual(sha256_file(source), sha256_file(restored))

    def test_large_file_is_split_without_changing_combined_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "large.bin"
            source.write_bytes(os.urandom(25000))
            parts = split_file(source, root / "parts", 8192)
            self.assertEqual(4, len(parts))
            self.assertEqual(source.read_bytes(), b"".join(path.read_bytes() for path in parts))


class _FakeBot:
    def __init__(self) -> None:
        self.send_document = AsyncMock(side_effect=self._send)
        self.delete_message = AsyncMock()
        self._message_id = 0

    async def _send(self, **kwargs):
        self._message_id += 1
        document = kwargs["document"]
        path = Path(document.path)
        return SimpleNamespace(
            message_id=self._message_id,
            document=SimpleNamespace(
                file_id=f"file-{self._message_id}",
                file_unique_id=f"unique-{self._message_id}",
                file_size=path.stat().st_size,
            ),
        )


class TelegramStorageUploaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_file_is_deleted_only_after_database_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "report.json"
            source.write_text('{"ok":true}', encoding="utf-8")
            settings = SimpleNamespace(
                chat_id=-1004459280894,
                threads=SimpleNamespace(for_kind=lambda kind: 11),
                staging_dir=root / "staging",
                max_part_bytes=1024 * 1024,
                delete_after_upload=True,
            )
            stored = StoredObject(
                object_id=9,
                kind="exports",
                logical_key="exports:report",
                sha256=sha256_file(source),
                size_bytes=source.stat().st_size,
                chat_id=settings.chat_id,
                thread_id=11,
                parts=(),
            )
            repository = SimpleNamespace(
                get_existing=AsyncMock(return_value=None),
                create_object=AsyncMock(return_value=stored),
                mark_local_deleted=AsyncMock(),
            )
            uploader = TelegramStorageUploader(
                bot=_FakeBot(),
                repository=repository,
                settings=settings,
            )
            candidate = StorageCandidate(
                kind="exports",
                path=source,
                logical_key="exports:report",
                original_name=source.name,
                delete_paths=(source,),
            )

            _, deleted, _, duplicate = await uploader.upload(candidate)

            self.assertFalse(duplicate)
            self.assertEqual(1, deleted)
            self.assertFalse(source.exists())
            repository.create_object.assert_awaited_once()
            repository.mark_local_deleted.assert_awaited_once_with(9)

    async def test_database_failure_keeps_local_file_and_removes_orphan_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "incident.log"
            source.write_text("traceback", encoding="utf-8")
            settings = SimpleNamespace(
                chat_id=-1004459280894,
                threads=SimpleNamespace(for_kind=lambda kind: 9),
                staging_dir=root / "staging",
                max_part_bytes=1024 * 1024,
                delete_after_upload=True,
            )
            bot = _FakeBot()
            repository = SimpleNamespace(
                get_existing=AsyncMock(return_value=None),
                create_object=AsyncMock(side_effect=RuntimeError("database unavailable")),
                mark_local_deleted=AsyncMock(),
            )
            uploader = TelegramStorageUploader(
                bot=bot,
                repository=repository,
                settings=settings,
            )
            candidate = StorageCandidate(
                kind="diagnostics",
                path=source,
                logical_key="diagnostics:incident",
                original_name=source.name,
                delete_paths=(source,),
            )

            with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                await uploader.upload(candidate)

            self.assertTrue(source.exists())
            bot.delete_message.assert_awaited_once()
            repository.mark_local_deleted.assert_not_awaited()


class TelegramStorageSourceContractTests(unittest.TestCase):
    def test_schema_and_registration_are_present(self) -> None:
        migration = Path("migrations/z003_telegram_storage_center.sql").read_text(
            encoding="utf-8"
        )
        owner_menu = Path(
            "velvet_bot/presentation/telegram/routers/"
            "core_operations_controllers/owner_menu.py"
        ).read_text(encoding="utf-8")
        controller = Path(
            "velvet_bot/presentation/telegram/storage_center.py"
        ).read_text(encoding="utf-8")
        service = Path(
            "velvet_bot/domains/telegram_storage/service.py"
        ).read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS telegram_storage_objects", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS telegram_storage_parts", migration)
        self.assertIn("telegram_storage_object_id", migration)
        self.assertIn("register_storage_center(router)", owner_menu)
        self.assertIn('Command("storage_migrate")', controller)
        self.assertIn("router.startup.register(handle_storage_startup)", controller)
        self.assertIn("STORAGE_THREAD_WATERMARKS", Path(".env.example").read_text())
        self.assertIn("AES-256-GCM+scrypt:v1", service)
        self.assertNotIn("analytics_controllers.channel", service)


if __name__ == "__main__":
    unittest.main()

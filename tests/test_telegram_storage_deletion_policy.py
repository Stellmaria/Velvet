from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.domains.telegram_storage.deletion import (
    DeletionPolicy,
    build_storage_deletion_policy,
    delete_paths,
)
from velvet_bot.domains.telegram_storage.files import sha256_file
from velvet_bot.domains.telegram_storage.models import StorageCandidate, StoredObject
from velvet_bot.domains.telegram_storage.uploader import TelegramStorageUploader


class TelegramStorageDeletionPolicyTests(unittest.TestCase):
    def _policy(
        self,
        root: Path,
        *,
        recursive: bool = False,
    ) -> DeletionPolicy:
        return DeletionPolicy(
            name="test-storage",
            allowed_roots=(root,),
            allow_recursive_directories=recursive,
        )

    def test_file_inside_allowlist_is_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "staging" / "result.json"
            source.parent.mkdir()
            source.write_text('{"ok":true}', encoding="utf-8")

            result = delete_paths((source,), policy=self._policy(root))

            self.assertTrue(result.complete)
            self.assertEqual(1, result.deleted_count)
            self.assertGreater(result.freed_bytes, 0)
            self.assertFalse(source.exists())

    def test_absolute_path_outside_allowlist_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            allowed = base / "allowed"
            allowed.mkdir()
            outside = base / "outside.txt"
            outside.write_text("keep", encoding="utf-8")

            result = delete_paths((outside,), policy=self._policy(allowed))

            self.assertFalse(result.complete)
            self.assertEqual("outside_allowlist", result.issues[0].code)
            self.assertTrue(outside.exists())

    def test_dotdot_cannot_escape_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            allowed = base / "allowed"
            allowed.mkdir()
            outside = base / "outside.txt"
            outside.write_text("keep", encoding="utf-8")
            escaped = allowed / "nested" / ".." / ".." / outside.name

            result = delete_paths((escaped,), policy=self._policy(allowed))

            self.assertEqual("outside_allowlist", result.issues[0].code)
            self.assertTrue(outside.exists())

    def test_symlink_to_external_file_deletes_only_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            allowed = base / "allowed"
            allowed.mkdir()
            outside = base / "outside.txt"
            outside.write_text("keep", encoding="utf-8")
            link = allowed / "external-link"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlink is unavailable: {error}")

            result = delete_paths((link,), policy=self._policy(allowed))

            self.assertTrue(result.complete)
            self.assertEqual(1, result.deleted_count)
            self.assertFalse(link.exists())
            self.assertTrue(outside.exists())

    def test_symlink_parent_to_external_directory_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            allowed = base / "allowed"
            allowed.mkdir()
            outside = base / "outside"
            outside.mkdir()
            target = outside / "target.txt"
            target.write_text("keep", encoding="utf-8")
            linked_directory = allowed / "linked"
            try:
                linked_directory.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"directory symlink is unavailable: {error}")

            result = delete_paths(
                (linked_directory / target.name,),
                policy=self._policy(allowed),
            )

            self.assertEqual("symlink_parent", result.issues[0].code)
            self.assertTrue(target.exists())
            self.assertTrue(linked_directory.is_symlink())

    def test_directory_requires_explicit_recursive_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / "tree"
            target.mkdir()
            (target / "item.txt").write_text("delete", encoding="utf-8")

            refused = delete_paths((target,), policy=self._policy(root))
            deleted = delete_paths(
                (target,),
                policy=self._policy(root, recursive=True),
            )

            self.assertEqual("recursive_not_allowed", refused.issues[0].code)
            self.assertTrue(deleted.complete)
            self.assertFalse(target.exists())

    def test_dry_run_returns_plan_without_deleting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "report.txt"
            source.write_text("keep for now", encoding="utf-8")

            result = self._policy(root).plan((source,))

            self.assertTrue(result.dry_run)
            self.assertTrue(result.complete)
            self.assertEqual(1, len(result.planned))
            self.assertEqual(0, result.deleted_count)
            self.assertTrue(source.exists())

    def test_allowlist_cannot_be_home_checkout_data_or_filesystem_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            data = project / "data"
            data.mkdir()
            for dangerous in (Path(project.anchor), Path.home(), project, data):
                with self.subTest(dangerous=dangerous):
                    with self.assertRaises(ValueError):
                        build_storage_deletion_policy(
                            name="dangerous",
                            roots=(dangerous,),
                            project_dir=project,
                            data_dir=data,
                        )

    def test_env_and_git_metadata_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            env_file = root / ".env.server"
            env_file.write_text("SECRET=value", encoding="utf-8")
            git_file = root / ".git" / "config"
            git_file.parent.mkdir()
            git_file.write_text("[core]", encoding="utf-8")

            result = delete_paths(
                (env_file, git_file),
                policy=self._policy(root),
            )

            self.assertEqual({"blocked_name"}, {issue.code for issue in result.issues})
            self.assertTrue(env_file.exists())
            self.assertTrue(git_file.exists())

    @unittest.skipIf(os.name == "nt", "POSIX test for foreign Windows path syntax")
    def test_foreign_windows_drive_path_is_invalid_on_posix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()

            result = delete_paths(
                (r"C:\Velvet\outside.txt",),
                policy=self._policy(root),
            )

            self.assertEqual("invalid_path", result.issues[0].code)


class TelegramStorageDeletionUploaderTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _stored(source: Path) -> StoredObject:
        return StoredObject(
            object_id=72,
            kind="exports",
            logical_key="exports:duplicate",
            sha256=sha256_file(source),
            size_bytes=source.stat().st_size,
            chat_id=-1004459280894,
            thread_id=11,
            parts=(),
        )

    async def test_duplicate_upload_uses_same_policy_and_keeps_external_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            allowed = base / "allowed"
            allowed.mkdir()
            source = base / "outside.json"
            source.write_text('{"keep":true}', encoding="utf-8")
            repository = SimpleNamespace(
                get_existing=AsyncMock(return_value=self._stored(source)),
                mark_local_deleted=AsyncMock(),
            )
            settings = SimpleNamespace(
                delete_after_upload=True,
                deletion_policy_for=lambda kind: DeletionPolicy(
                    name=f"test-{kind}",
                    allowed_roots=(allowed,),
                ),
            )
            uploader = TelegramStorageUploader(
                bot=SimpleNamespace(),
                repository=repository,
                settings=settings,
            )
            candidate = StorageCandidate(
                kind="exports",
                path=source,
                logical_key="exports:duplicate",
                original_name=source.name,
                delete_paths=(source,),
            )

            _, deleted, freed, duplicate = await uploader.upload(candidate)

            self.assertTrue(duplicate)
            self.assertEqual((deleted, freed), (0, 0))
            self.assertTrue(source.exists())
            repository.mark_local_deleted.assert_not_awaited()

    async def test_delete_error_does_not_mark_object_local_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "report.json"
            source.write_text('{"keep":true}', encoding="utf-8")
            repository = SimpleNamespace(
                get_existing=AsyncMock(return_value=self._stored(source)),
                mark_local_deleted=AsyncMock(),
            )
            settings = SimpleNamespace(
                delete_after_upload=True,
                deletion_policy_for=lambda kind: DeletionPolicy(
                    name=f"test-{kind}",
                    allowed_roots=(root,),
                ),
            )
            uploader = TelegramStorageUploader(
                bot=SimpleNamespace(),
                repository=repository,
                settings=settings,
            )
            candidate = StorageCandidate(
                kind="exports",
                path=source,
                logical_key="exports:duplicate",
                original_name=source.name,
                delete_paths=(source,),
            )

            with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
                _, deleted, _, duplicate = await uploader.upload(candidate)

            self.assertTrue(duplicate)
            self.assertEqual(0, deleted)
            self.assertTrue(source.exists())
            repository.mark_local_deleted.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

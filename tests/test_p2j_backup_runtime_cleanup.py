from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from velvet_bot.backup_runtime import BackupService
from velvet_bot.backup_service import BackupValidation


class BackupRuntimeCleanupTests(unittest.IsolatedAsyncioTestCase):
    def _service(self, directory: Path, *, cancel: bool) -> BackupService:
        service = BackupService(
            database_url="postgresql://example",
            backup_dir=directory,
            pg_dump_path="pg_dump",
            pg_restore_path="pg_restore",
        )
        service._executable = lambda configured, label: "pg_dump"

        async def run_process(*arguments: str):
            output = Path(arguments[arguments.index("--file") + 1])
            output.write_bytes(b"dump")
            return 0, "", ""

        async def validate(*args, **kwargs):
            if cancel:
                raise asyncio.CancelledError
            return BackupValidation(
                valid=True,
                readable=True,
                size_bytes=4,
                sha256="hash",
                expected_tables=(),
                discovered_tables=(),
                missing_tables=(),
                schema_version=None,
                current_schema_version=None,
                schema_matches=True,
                message="ok",
            )

        def write_manifest(path: Path, **kwargs) -> None:
            service._manifest_path(path).write_text("{}", encoding="utf-8")
            raise RuntimeError("manifest failed")

        service._run_process = run_process
        service._validate_dump = validate
        service._write_manifest = write_manifest
        return service

    async def test_manifest_failure_removes_dump_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            directory = Path(value)
            service = self._service(directory, cancel=False)
            with self.assertRaises(RuntimeError):
                await service._create_dump_file(
                    backup_kind="manual",
                    expected_tables=(),
                    schema_version=None,
                    current_schema_version=None,
                    created_by=None,
                )
            self.assertEqual(list(directory.iterdir()), [])

    async def test_cancellation_removes_created_dump(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            directory = Path(value)
            service = self._service(directory, cancel=True)
            with self.assertRaises(asyncio.CancelledError):
                await service._create_dump_file(
                    backup_kind="manual",
                    expected_tables=(),
                    schema_version=None,
                    current_schema_version=None,
                    created_by=None,
                )
            self.assertEqual(list(directory.iterdir()), [])


if __name__ == "__main__":
    unittest.main()

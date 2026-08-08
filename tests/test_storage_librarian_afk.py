from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from velvet_bot.domains.telegram_storage.librarian_afk_repository import (
    StorageLibrarianAfkRepository,
)
from velvet_bot.domains.telegram_storage.librarian_models import (
    LibrarianObject,
    StorageLibrarianSettings,
)
from velvet_bot.infrastructure.telegram.storage_librarian_reports import (
    build_storage_librarian_failure_report,
)
from velvet_bot.presentation.telegram.storage_librarian import (
    _auto_allowed_kinds,
    _env_int,
)


ROOT = Path(__file__).resolve().parents[1]


def _settings() -> StorageLibrarianSettings:
    return StorageLibrarianSettings(
        enabled=True,
        hermes_base_url="http://librarian-hermes:8642",
        hermes_api_key="x" * 24,
        scan_interval_seconds=300,
        poll_interval_seconds=2,
        run_timeout_seconds=900,
        max_object_bytes=12 * 1024 * 1024,
        max_text_chars=120_000,
        max_zip_entries=40,
        max_attempts=3,
        analyzer_version="test:v1",
        allowed_kinds=(
            "diagnostics",
            "exports",
            "codex",
            "releases",
            "rework",
            "inbox",
        ),
    )


class StorageLibrarianAfkContractTests(unittest.TestCase):
    def test_afk_defaults_are_bounded(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(("diagnostics", "releases"), _auto_allowed_kinds(_settings()))
            self.assertEqual(
                1,
                _env_int(
                    "STORAGE_LIBRARIAN_AUTO_BATCH_SIZE",
                    1,
                    minimum=1,
                    maximum=10,
                ),
            )

    def test_afk_kinds_are_intersected_with_manual_allowlist(self) -> None:
        with patch.dict(
            os.environ,
            {"STORAGE_LIBRARIAN_AUTO_ALLOWED_KINDS": "diagnostics,backups,analysis"},
            clear=True,
        ):
            self.assertEqual(("diagnostics",), _auto_allowed_kinds(_settings()))

    def test_afk_repository_rejects_missing_cutoff(self) -> None:
        with self.assertRaises(ValueError):
            StorageLibrarianAfkRepository(object(), min_object_id=0)  # type: ignore[arg-type]

    def test_afk_cutoff_and_scripts_fail_closed(self) -> None:
        presentation = (
            ROOT / "velvet_bot/presentation/telegram/storage_librarian.py"
        ).read_text(encoding="utf-8")
        repository = (
            ROOT / "velvet_bot/domains/telegram_storage/librarian_repository.py"
        ).read_text(encoding="utf-8")
        afk_repository = (
            ROOT / "velvet_bot/domains/telegram_storage/librarian_afk_repository.py"
        ).read_text(encoding="utf-8")
        application = (
            ROOT / "velvet_bot/application/storage_librarian.py"
        ).read_text(encoding="utf-8")
        enable = (ROOT / "deploy/hermes-librarian/enable_afk.sh").read_text(
            encoding="utf-8"
        )
        full_archive = (
            ROOT / "deploy/hermes-librarian/enable_full_archive.sh"
        ).read_text(encoding="utf-8")
        disable = (ROOT / "deploy/hermes-librarian/disable_afk.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID", presentation)
        self.assertIn("STORAGE_LIBRARIAN_AUTO_BACKFILL", presentation)
        self.assertIn("StorageLibrarianAfkRepository", presentation)
        self.assertIn("service.repository = repository", presentation)
        self.assertIn("enqueue_newer_than", presentation)
        self.assertIn("enqueue_pending", presentation)
        self.assertIn("process_once(auto_enqueue=False)", presentation)
        self.assertIn("auto_enqueue: bool = False", application)
        self.assertIn("await asyncio.sleep(settings.scan_interval_seconds)", presentation)
        self.assertIn("o.id > $1::BIGINT", repository)
        self.assertIn("storage_object_id > $2::BIGINT", afk_repository)
        self.assertIn("ON CONFLICT (storage_object_id) DO NOTHING", repository)
        self.assertIn("SELECT COALESCE(MAX(id), 0)", enable)
        self.assertIn('"STORAGE_LIBRARIAN_AUTO_ENQUEUE": "true"', enable)
        self.assertIn('"STORAGE_LIBRARIAN_AUTO_BACKFILL": "false"', enable)
        self.assertIn('"STORAGE_LIBRARIAN_AUTO_ENQUEUE": "true"', full_archive)
        self.assertIn('"STORAGE_LIBRARIAN_AUTO_BACKFILL": "true"', full_archive)
        self.assertIn('"STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID": "0"', full_archive)
        self.assertIn('"STORAGE_LIBRARIAN_AUTO_BATCH_SIZE": str(batch_size)', full_archive)
        self.assertIn("http://ollama-librarian:11434", full_archive)
        self.assertIn('"STORAGE_LIBRARIAN_AUTO_ENQUEUE": "false"', disable)
        self.assertIn('"STORAGE_LIBRARIAN_AUTO_BACKFILL": "false"', disable)

    def test_full_archive_mode_is_explicit_bounded_and_local(self) -> None:
        presentation = (
            ROOT / "velvet_bot/presentation/telegram/storage_librarian.py"
        ).read_text(encoding="utf-8")
        full_archive = (
            ROOT / "deploy/hermes-librarian/enable_full_archive.sh"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'full_archive = _env_enabled("STORAGE_LIBRARIAN_AUTO_BACKFILL", False)',
            presentation,
        )
        self.assertIn("if full_archive:", presentation)
        self.assertIn("repository.enqueue_pending(", presentation)
        self.assertIn("limit=batch_size", presentation)
        self.assertIn(
            "Full-archive режим требует STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID=0",
            presentation,
        )
        self.assertIn("AFK full-archive: <b>активен</b>", presentation)
        self.assertIn(
            'AUTO_BATCH_SIZE="${STORAGE_LIBRARIAN_AUTO_BATCH_SIZE:-1}"',
            full_archive,
        )
        self.assertIn(
            'SCAN_INTERVAL="${STORAGE_LIBRARIAN_SCAN_INTERVAL_SECONDS:-60}"',
            full_archive,
        )
        self.assertIn("local Ollama only", full_archive)

    def test_full_archive_scheduler_is_owned_by_application_lifecycle(self) -> None:
        bootstrap = (ROOT / "velvet_bot/app/bootstrap.py").read_text(
            encoding="utf-8"
        )
        repository = (
            ROOT / "velvet_bot/domains/telegram_storage/librarian_repository.py"
        ).read_text(encoding="utf-8")

        self.assertIn("await start_storage_librarian(bot, database)", bootstrap)
        self.assertIn("await stop_storage_librarian()", bootstrap)
        self.assertIn(
            "LEFT JOIN telegram_storage_analysis_jobs AS existing_job",
            repository,
        )
        self.assertIn("existing_job.storage_object_id IS NULL", repository)
        self.assertIn(
            "existing_job.status IN ('completed', 'skipped')",
            repository,
        )
        self.assertNotIn(
            "existing_job.status IN ('completed', 'skipped', 'failed')",
            repository,
        )

    def test_terminal_failure_report_is_redacted_and_non_mutating(self) -> None:
        item = LibrarianObject(
            object_id=2201,
            storage_kind="diagnostics",
            logical_key="diagnostics:logs:test",
            original_name="test.log",
            mime_type="text/plain",
            size_bytes=100,
            sha256="a" * 64,
            encrypted=False,
            manifest={},
            parts=(),
        )
        report = build_storage_librarian_failure_report(
            object_id=2201,
            item=item,
            error=RuntimeError("API_KEY=super-secret-value failed"),
        )
        self.assertIn("Storage ID: <code>2201</code>", report)
        self.assertIn("[REDACTED]", report)
        self.assertNotIn("super-secret-value", report)
        self.assertIn("перезапуск, обновление или откат не выполнялись", report)


if __name__ == "__main__":
    unittest.main()

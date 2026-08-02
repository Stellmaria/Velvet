from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from velvet_bot.domains.telegram_storage.librarian_models import LibrarianObject
from velvet_bot.infrastructure.telegram.storage_librarian_reports import (
    build_storage_librarian_failure_report,
)
from velvet_bot.presentation.telegram.storage_librarian import (
    _auto_allowed_kinds,
    _env_int,
)
from velvet_bot.domains.telegram_storage.librarian_models import (
    StorageLibrarianSettings,
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

    def test_afk_cutoff_and_scripts_fail_closed(self) -> None:
        presentation = (
            ROOT / "velvet_bot/presentation/telegram/storage_librarian.py"
        ).read_text(encoding="utf-8")
        repository = (
            ROOT / "velvet_bot/domains/telegram_storage/librarian_repository.py"
        ).read_text(encoding="utf-8")
        enable = (ROOT / "deploy/hermes-librarian/enable_afk.sh").read_text(
            encoding="utf-8"
        )
        disable = (ROOT / "deploy/hermes-librarian/disable_afk.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID", presentation)
        self.assertIn("enqueue_newer_than", presentation)
        self.assertIn("process_once(auto_enqueue=False)", presentation)
        self.assertIn("await asyncio.sleep(settings.scan_interval_seconds)", presentation)
        self.assertIn("o.id > $1::BIGINT", repository)
        self.assertIn("ON CONFLICT (storage_object_id) DO NOTHING", repository)
        self.assertIn("SELECT COALESCE(MAX(id), 0)", enable)
        self.assertIn("STORAGE_LIBRARIAN_AUTO_ENQUEUE=true", enable)
        self.assertIn("STORAGE_LIBRARIAN_AUTO_ENQUEUE=false", disable)
        self.assertNotIn("enqueue_pending(settings=settings)", presentation)

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
        self.assertIn("restart/update/rollback не выполнялось", report)


if __name__ == "__main__":
    unittest.main()

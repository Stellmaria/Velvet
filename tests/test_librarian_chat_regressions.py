from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from velvet_bot.core.config.arthur import ArthurSettings


ROOT = Path(__file__).resolve().parents[1]


class LibrarianInstallerRegressionTests(unittest.TestCase):
    def test_installer_preserves_operator_analyzer_and_running_bot_image(self) -> None:
        installer = (
            ROOT / "deploy" / "hermes-librarian" / "install.sh"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'values.get("STORAGE_LIBRARIAN_ANALYZER_VERSION", "").strip()',
            installer,
        )
        self.assertIn(
            '"STORAGE_LIBRARIAN_ANALYZER_VERSION": analyzer_version',
            installer,
        )
        self.assertIn('"$SOURCE_DIR/recreate_bot_preserving_image.sh"', installer)
        self.assertNotIn(
            "docker compose --env-file '$VELVET_ENV_FILE' -f '$VELVET_COMPOSE_FILE' \\\n    up -d --force-recreate bot",
            installer,
        )
        self.assertIn('"Analyzer version preserved: $ANALYZER_VERSION."', installer)


class ArthurReportTargetRegressionTests(unittest.TestCase):
    def _settings(self, **extra: str) -> ArthurSettings:
        environment = {
            "ARTHUR_BOT_TOKEN": "arthur-token",
            "BOT_TOKEN": "velvet-token",
            "DATABASE_URL": "postgresql://velvet:velvet@postgres/velvet",
            "ARTHUR_ALLOWED_USER_IDS": "123",
            "ARTHUR_STORAGE_GATEWAY_API_KEY": "x" * 32,
            "STORAGE_LIBRARIAN_AUTO_ENQUEUE": "false",
            **extra,
        }
        with patch.dict(os.environ, environment, clear=True):
            return ArthurSettings.from_env()

    def test_reports_are_disabled_without_explicit_arthur_target(self) -> None:
        settings = self._settings(
            TELEGRAM_STORAGE_CHAT_ID="-1004459280894",
            STORAGE_THREAD_ANALYSIS="2478",
        )

        self.assertIsNone(settings.report_chat_id)
        self.assertIsNone(settings.report_thread_id)

    def test_explicit_arthur_report_target_is_preserved(self) -> None:
        settings = self._settings(
            ARTHUR_REPORT_CHAT_ID="123",
            ARTHUR_REPORT_THREAD_ID="456",
        )

        self.assertEqual(123, settings.report_chat_id)
        self.assertEqual(456, settings.report_thread_id)


class ArthurArchiveStatusRegressionTests(unittest.TestCase):
    def test_archive_status_labels_live_backlog_and_totals(self) -> None:
        presentation = (
            ROOT
            / "velvet_bot"
            / "presentation"
            / "telegram"
            / "arthur_librarian.py"
        ).read_text(encoding="utf-8")

        self.assertIn("Queued now (live backlog):", presentation)
        self.assertIn("Running now:", presentation)
        self.assertIn("Completed total:", presentation)
        self.assertIn("Skipped total:", presentation)
        self.assertIn("Failed total:", presentation)


if __name__ == "__main__":
    unittest.main()

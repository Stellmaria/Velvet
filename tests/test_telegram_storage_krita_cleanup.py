from __future__ import annotations

import logging
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from velvet_bot.domains.telegram_storage.models import TelegramStorageSettings
from velvet_bot.domains.telegram_storage.service import TelegramStorageMigrationService
from velvet_bot.domains.telegram_storage import service as storage_service


class TelegramStorageKritaCleanupTests(unittest.TestCase):
    @staticmethod
    def _settings(project: Path, bridge: Path) -> TelegramStorageSettings:
        with patch.dict(
            os.environ,
            {
                "SUPERVISOR_PROJECT_DIR": str(project),
                "KRITA_BRIDGE_DIR": str(bridge),
                "STORAGE_ENCRYPTION_SECRET": "x" * 32,
                "STORAGE_DELETE_AFTER_UPLOAD": "false",
            },
            clear=True,
        ):
            return TelegramStorageSettings.from_env()

    @staticmethod
    def _service(settings: TelegramStorageSettings) -> TelegramStorageMigrationService:
        return TelegramStorageMigrationService(
            bot=SimpleNamespace(),
            database=SimpleNamespace(),
            settings=settings,
        )

    def test_service_uses_settings_bridge_root_after_environment_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            configured = project / "configured-bridge"
            settings = self._settings(project, configured)
            with patch.dict(
                os.environ,
                {"KRITA_BRIDGE_DIR": str(project / "wrong-bridge")},
                clear=False,
            ):
                service = self._service(settings)

            self.assertEqual(configured.resolve(), service.bridge.paths.root)
            self.assertFalse((project / "wrong-bridge").exists())

    def test_missing_legacy_path_is_excluded_at_debug_level(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            service = self._service(self._settings(project, project / "bridge"))
            missing = project / "old-windows-bridge" / "sources" / "stale.png"

            with patch.object(storage_service.logger, "log") as log:
                safe = service._safe_bridge_paths((missing,))

            self.assertEqual((), safe)
            log.assert_called_once()
            self.assertEqual(logging.DEBUG, log.call_args.args[0])

    def test_existing_external_path_remains_a_warning_and_is_not_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            service = self._service(self._settings(project, project / "bridge"))
            outside = project / "outside.png"
            outside.write_bytes(b"keep")

            with patch.object(storage_service.logger, "log") as log:
                safe = service._safe_bridge_paths((outside,))

            self.assertEqual((), safe)
            log.assert_called_once()
            self.assertEqual(logging.WARNING, log.call_args.args[0])
            self.assertTrue(outside.exists())

    def test_file_inside_configured_bridge_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            bridge = project / "bridge"
            service = self._service(self._settings(project, bridge))
            source = service.bridge.paths.sources / "source.png"
            source.write_bytes(b"source")

            self.assertEqual((source.resolve(),), service._safe_bridge_paths((source,)))


if __name__ == "__main__":
    unittest.main()

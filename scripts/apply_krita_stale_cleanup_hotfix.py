from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "velvet_bot" / "domains" / "telegram_storage" / "service.py"
TEST = ROOT / "tests" / "test_telegram_storage_krita_cleanup.py"
WORKLOG = ROOT / "docs" / "worklog" / "2026-08-01-krita-stale-cleanup-warning.md"
WORKFLOW = ROOT / ".github" / "workflows" / "apply-krita-stale-cleanup-hotfix.yml"
SELF = Path(__file__).resolve()


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


service = SERVICE.read_text(encoding="utf-8")
service = replace_once(
    service,
    "from velvet_bot.infrastructure.krita_bridge import KritaBridge, default_krita_bridge_dir",
    "from velvet_bot.infrastructure.krita_bridge import KritaBridge",
    label="krita bridge import",
)
service = replace_once(
    service,
    "        self.bridge = KritaBridge(default_krita_bridge_dir())",
    "        self.bridge = KritaBridge(self.settings.krita_bridge_dir)",
    label="configured bridge root",
)
service = replace_once(
    service,
    '                logger.warning("Refusing to delete path outside Krita bridge: %s", value)',
    '                logger.log(logging.WARNING if Path(value).exists() or Path(value).is_symlink() else logging.DEBUG, "Refusing to delete path outside Krita bridge: %s", value)',
    label="stale cleanup logging",
)
SERVICE.write_text(service, encoding="utf-8")

TEST.write_text(
    '''from __future__ import annotations

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
''',
    encoding="utf-8",
)

WORKLOG.parent.mkdir(parents=True, exist_ok=True)
WORKLOG.write_text(
    '''# 2026-08-01 — Устранение повторного предупреждения очистки Krita bridge

- Дата: `2026-08-01`
- ID: `krita-stale-cleanup-warning`
- Линия/фаза: `production hotfix`
- Статус: `завершено`
- Ветка: `hotfix/krita-stale-cleanup-warning`

## Причина

Telegram Storage создавал `KritaBridge` повторным чтением `KRITA_BRIDGE_DIR`, а не из уже проверенного `TelegramStorageSettings`. После переноса с Windows в базе остались старые пути вида `E:\\VelvetKritaBridge\\sources\\...`. На Linux они не существуют, но каждая фоновая очистка снова записывала WARNING `Refusing to delete path outside Krita bridge`, из-за чего один безопасно отклонённый исторический путь бесконечно поднимал инцидент #104.

## Исправление

- `TelegramStorageMigrationService` использует канонический `settings.krita_bridge_dir`;
- отсутствующий путь вне текущего bridge остаётся отклонённым, но записывается только на DEBUG;
- существующий внешний путь по-прежнему отклоняется с WARNING;
- добавлены тесты на drift env/settings, старый отсутствующий путь, существующий внешний путь и допустимый файл внутри bridge.

## Безопасность

Allowlist не расширен. Исправление не удаляет старый Windows-путь и не разрешает удаление вне текущего Krita bridge. Оно лишь перестаёт считать несуществующую историческую запись рабочей аварией.

## Проверка после deployment

После обновления production старый occurrence #104 можно отметить прочитанным. Новый счётчик не должен расти. Если появится WARNING с реально существующим внешним путём, это отдельная конфигурационная ошибка и её нельзя автоматически подавлять.
''',
    encoding="utf-8",
)

# Refresh generated package inventory because the service AST changed. Keep the
# checked numerical contract synchronized with the generated source of truth.
import subprocess
import sys

subprocess.run(
    [
        sys.executable,
        str(ROOT / "scripts" / "inventory_package_architecture.py"),
        "--write",
        "--label",
        "p1-package-architecture-baseline",
    ],
    cwd=ROOT,
    check=True,
)

inventory = json.loads(
    (ROOT / "docs" / "package_architecture_inventory.json").read_text(encoding="utf-8")
)
loc = int(inventory["production_loc"])
contract_path = ROOT / "tests" / "test_package_architecture_inventory.py"
contract = contract_path.read_text(encoding="utf-8")
contract, count_numeric = re.subn(
    r'self\.assertEqual\([0-9_]+, self\.inventory\["production_loc"\]\)',
    f'self.assertEqual({loc:_}, self.inventory["production_loc"])',
    contract,
    count=1,
)
contract, count_markdown = re.subn(
    r'Production LOC: \*\*[0-9]+\*\*',
    f'Production LOC: **{loc}**',
    contract,
    count=1,
)
if count_numeric != 1 or count_markdown != 1:
    raise RuntimeError("Could not synchronize package architecture LOC contract")
contract_path.write_text(contract, encoding="utf-8")

WORKFLOW.unlink(missing_ok=True)
SELF.unlink(missing_ok=True)

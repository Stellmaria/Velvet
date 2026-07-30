from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class AufRuntimeBrandBoundaryTests(unittest.TestCase):
    def test_application_installs_only_canonical_auf_entrypoints(self) -> None:
        source = _read("velvet_bot/app/__init__.py")
        self.assertIn("install_auf_cancel_ui", source)
        self.assertIn("install_auf_runtime_dispatcher", source)
        self.assertIn("install_auf_workspace_ui", source)
        self.assertNotIn("install_meow_cancel_ui", source)
        self.assertNotIn("install_meow_runtime_dispatcher", source)
        self.assertNotIn("install_meow_workspace_ui", source)

    def test_legacy_installers_are_thin_compatibility_shims(self) -> None:
        expected = {
            "velvet_bot/app/meow_cancel_ui_install.py": "install_meow_cancel_ui",
            "velvet_bot/app/meow_runtime_install.py": "install_meow_runtime_dispatcher",
            "velvet_bot/app/meow_workspace_ui_install.py": "install_meow_workspace_ui",
        }
        for path, legacy_name in expected.items():
            with self.subTest(path=path):
                source = _read(path)
                self.assertIn("Compatibility shim", source)
                self.assertIn(legacy_name, source)
                self.assertLessEqual(len(source.splitlines()), 14)

    def test_legacy_runtime_modules_are_only_compatibility_shims(self) -> None:
        expected = {
            "velvet_bot/domains/meow_runtime/models.py": "AufProvider",
            "velvet_bot/domains/meow_runtime/store.py": "AufRuntimeRepository",
            "velvet_bot/domains/meow_runtime/service.py": "AufRuntimeService",
            "velvet_bot/domains/meow_runtime/queue.py": "ProviderAufTaskQueueService",
            "velvet_bot/domains/meow_runtime/dispatcher.py": "AufGenerationDispatcher",
            "velvet_bot/domains/meow_runtime/cancellable_worker.py": "AufCancellationRequested",
        }
        for path, canonical_name in expected.items():
            with self.subTest(path=path):
                source = _read(path)
                self.assertIn("Compatibility alias", source)
                self.assertIn(canonical_name, source)
                self.assertLessEqual(len(source.splitlines()), 25)

    def test_canonical_runtime_does_not_import_retired_package(self) -> None:
        paths = (
            "velvet_bot/domains/auf_runtime/__init__.py",
            "velvet_bot/domains/auf_runtime/models.py",
            "velvet_bot/domains/auf_runtime/store.py",
            "velvet_bot/domains/auf_runtime/service.py",
            "velvet_bot/domains/auf_runtime/queue.py",
            "velvet_bot/domains/auf_runtime/dispatcher.py",
            "velvet_bot/domains/auf_runtime/cancellable_worker.py",
            "velvet_bot/app/auf_runtime_install.py",
        )
        for path in paths:
            with self.subTest(path=path):
                source = _read(path)
                self.assertNotIn("velvet_bot.domains.meow_runtime", source)
                self.assertNotIn("class Meow", source)
                self.assertNotIn("ProviderMeow", source)

    def test_primary_auf_screens_have_no_retired_russian_brand(self) -> None:
        paths = (
            "velvet_bot/app/auf_runtime_install.py",
            "velvet_bot/app/auf_workspace_ui_install.py",
            "velvet_bot/presentation/telegram/routers/workspace_auf_root.py",
            "velvet_bot/presentation/telegram/routers/workspace_auf_runtime.py",
            "velvet_bot/presentation/telegram/routers/workspace_auf_photo.py",
            "velvet_bot/presentation/telegram/workspace_home_presentation.py",
            "velvet_bot/domains/auf_runtime/service.py",
            "velvet_bot/domains/auf_runtime/store.py",
        )
        for path in paths:
            with self.subTest(path=path):
                source = _read(path)
                self.assertNotIn("Мяу", source)
                self.assertNotIn("мяу", source)

    def test_legacy_transport_keys_are_centralized(self) -> None:
        canonical = _read("velvet_bot/domains/auf_runtime/__init__.py")
        home = _read("velvet_bot/presentation/telegram/workspace_home_presentation.py")
        self.assertIn('AUF_MODULE_KEY = "auf"', canonical)
        self.assertIn('AUF_WORKSPACE_ACTION = "auf"', canonical)
        self.assertIn('LEGACY_AUF_WORKSPACE_ACTION = "meow"', canonical)
        self.assertNotIn('item.module_key == "meow"', home)
        self.assertNotIn('workspace_callback("meow"', home)

    def test_dispatcher_exposes_only_canonical_auf_di_keys(self) -> None:
        source = _read("velvet_bot/app/dispatcher.py")
        self.assertIn('"auf_runtime_service": auf_runtime_service', source)
        self.assertIn('"auf_wallet_service": auf_wallet_service', source)
        self.assertIn('"auf_purchase_service": auf_purchase_service', source)
        self.assertNotIn('"meow_runtime_service"', source)
        self.assertNotIn('"meow_wallet_service"', source)
        self.assertNotIn('"meow_purchase_service"', source)
        self.assertIn("from velvet_bot.domains.auf_runtime", source)

    def test_package_init_does_not_reintroduce_meow_catalog_entries(self) -> None:
        source = _read("velvet_bot/__init__.py")
        self.assertNotIn('MODULE_LABELS["meow"]', source)
        self.assertNotIn('MODULE_HELP["meow"]', source)


if __name__ == "__main__":
    unittest.main()

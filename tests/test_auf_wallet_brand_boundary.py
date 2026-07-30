from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class AufWalletBrandBoundaryTests(unittest.TestCase):
    def test_canonical_wallet_never_imports_retired_package(self) -> None:
        for path in (
            "velvet_bot/domains/auf_wallet/__init__.py",
            "velvet_bot/domains/auf_wallet/models.py",
            "velvet_bot/domains/auf_wallet/store.py",
            "velvet_bot/domains/auf_wallet/service.py",
            "velvet_bot/domains/auf_wallet/pricing.py",
            "velvet_bot/domains/auf_wallet/purchase.py",
            "velvet_bot/domains/auf_wallet/charged_queue.py",
            "velvet_bot/presentation/telegram/routers/workspace_auf_wallet.py",
            "velvet_bot/app/auf_wallet_ui_install.py",
        ):
            with self.subTest(path=path):
                source = _read(path)
                self.assertNotIn("velvet_bot.domains.meow_wallet", source)
                self.assertNotIn("class Meow", source)

    def test_retired_wallet_files_are_only_compatibility_shims(self) -> None:
        limits = {
            "velvet_bot/domains/meow_wallet/models.py": 40,
            "velvet_bot/domains/meow_wallet/store.py": 12,
            "velvet_bot/domains/meow_wallet/service.py": 20,
            "velvet_bot/domains/meow_wallet/pricing.py": 20,
            "velvet_bot/domains/meow_wallet/purchase.py": 25,
            "velvet_bot/domains/meow_wallet/charged_queue.py": 16,
            "velvet_bot/presentation/telegram/routers/workspace_meow_wallet.py": 10,
            "velvet_bot/app/meow_wallet_ui_install.py": 12,
        }
        for path, maximum in limits.items():
            with self.subTest(path=path):
                source = _read(path)
                self.assertIn("Compatibility", source)
                self.assertLessEqual(len(source.splitlines()), maximum)

    def test_production_uses_canonical_wallet_imports(self) -> None:
        dispatcher = _read("velvet_bot/app/dispatcher.py")
        installer = _read("velvet_bot/app/auf_wallet_ui_install.py")
        self.assertIn("from velvet_bot.domains.auf_wallet", dispatcher)
        self.assertIn("workspace_auf_wallet", installer)
        self.assertNotIn("meow_wallet_service", installer)
        self.assertNotIn("meow_purchase_service", installer)


if __name__ == "__main__":
    unittest.main()

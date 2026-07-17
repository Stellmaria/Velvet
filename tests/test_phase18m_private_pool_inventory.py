from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "inventory_private_pool.py"
SPEC = importlib.util.spec_from_file_location("inventory_private_pool", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Не удалось загрузить scripts/inventory_private_pool.py")
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


class PrivatePoolInventoryTests(unittest.TestCase):
    def test_production_clients_do_not_use_private_pool(self) -> None:
        findings = inventory.external_findings(inventory.collect_findings(ROOT))
        self.assertEqual((), findings, inventory.format_findings(findings))

    def test_database_internal_access_is_classified_as_allowed(self) -> None:
        findings = inventory.collect_findings(ROOT)
        internal = tuple(item for item in findings if item.allowed_internal)
        self.assertTrue(internal)
        self.assertTrue(all(item.path == "velvet_bot/database.py" for item in internal))
        self.assertTrue(all(item.class_name == "Database" for item in internal))

    def test_dynamic_getattr_is_detected_as_external(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "velvet_bot"
            package.mkdir()
            (package / "database.py").write_text(
                "class Database:\n"
                "    def _require_pool(self):\n"
                "        return None\n"
                "    def internal(self):\n"
                "        return self._require_pool()\n",
                encoding="utf-8",
            )
            (package / "client.py").write_text(
                "def external(database):\n"
                "    return getattr(database, '_require_pool')()\n",
                encoding="utf-8",
            )
            findings = inventory.collect_findings(root)

        external = inventory.external_findings(findings)
        self.assertEqual(1, len(external))
        self.assertEqual("dynamic_getattr", external[0].access_kind)
        self.assertEqual("velvet_bot/client.py", external[0].path)
        internal = tuple(item for item in findings if item.allowed_internal)
        self.assertEqual(1, len(internal))


if __name__ == "__main__":
    unittest.main()

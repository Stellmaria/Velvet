from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "inventory_private_pool.py"
MODULE_NAME = "inventory_private_pool"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Не удалось загрузить scripts/inventory_private_pool.py")
inventory = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = inventory
SPEC.loader.exec_module(inventory)


class PrivatePoolInventoryTests(unittest.TestCase):
    def test_production_private_pool_matches_reviewed_baseline(self) -> None:
        findings = inventory.collect_findings(ROOT)
        baseline = inventory.load_baseline()
        errors = inventory.compare_with_baseline(findings, baseline)
        self.assertEqual((), errors, inventory.format_baseline_errors(errors))
        self.assertEqual(12, len(inventory.external_findings(findings)))
        self.assertEqual(7, len(inventory.summarize_external(findings)))

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

    def test_baseline_rejects_new_external_file(self) -> None:
        finding = inventory.PrivatePoolFinding(
            path="velvet_bot/new_client.py",
            line=10,
            column=4,
            access_kind="attribute",
            class_name=None,
            function_name="load",
            allowed_internal=False,
        )
        baseline = {
            "schema_version": 1,
            "total_external_findings": 0,
            "total_files": 0,
            "files": [],
        }
        errors = inventory.compare_with_baseline((finding,), baseline)
        self.assertTrue(any("Новое внешнее обращение" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

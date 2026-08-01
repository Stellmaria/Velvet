from __future__ import annotations

import json
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "inventory_package_architecture.py"
INVENTORY_PATH = ROOT / "docs" / "package_architecture_inventory.json"
EXEMPTIONS_PATH = ROOT / "docs" / "package_architecture_exemptions.json"
MARKDOWN_PATH = ROOT / "docs" / "package_architecture_inventory.md"
PREVIEW_WORKFLOW = ROOT / ".github" / "workflows" / "package-architecture-preview.yml"

REQUIRED_EXCEPTION_FIELDS = {
    "id",
    "owner",
    "reason",
    "consumers",
    "replacement",
    "removal_condition",
    "regression_test",
    "issue",
}
EXPECTED_CATEGORIES = {
    "database-acquire-outside-persistence",
    "domain-aiogram-import",
    "domain-layer-import",
    "dynamic-import",
    "foreign-assignment",
    "installed-sentinel",
    "installer-like-module",
    "method-assign-ignore",
    "monolithic-function",
    "monolithic-module-loc",
    "package-getattr-side-effect",
    "sql-outside-persistence",
    "type-ignore-usage",
    "typing-any-usage",
}
EXPECTED_BURN_DOWN_ISSUES = {"#455", "#457", "#458", "#459", "#460", "#463"}


class PackageArchitectureInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--check",
                "--label",
                "p1-package-architecture-baseline",
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
        )
        if completed.returncode:
            raise AssertionError(
                "Package architecture inventory contract failed:\n"
                + completed.stderr
                + "\n"
                + completed.stdout
            )
        cls.inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        cls.exemptions = json.loads(EXEMPTIONS_PATH.read_text(encoding="utf-8"))
        cls.markdown = MARKDOWN_PATH.read_text(encoding="utf-8")

    def test_inventory_covers_the_complete_current_package(self) -> None:
        modules = self.inventory["modules"]
        self.assertEqual(639, self.inventory["production_module_count"])
        self.assertEqual(self.inventory["production_module_count"], len(modules))
        self.assertEqual(138_918, self.inventory["production_loc"])
        self.assertEqual(113, self.inventory["root_module_count"])
        self.assertEqual(0, self.inventory["root_unclassified_count"])
        self.assertEqual(84, self.inventory["router_count"])
        self.assertEqual(0, self.inventory["router_duplicate_count"])
        self.assertEqual(42, self.inventory["repository_module_count"])
        self.assertEqual(28, len(self.inventory["installer_graph"]))

        self.assertEqual(
            self.inventory["production_module_count"],
            sum(self.inventory["layer_counts"].values()),
        )
        for module in modules:
            with self.subTest(path=module["path"]):
                self.assertTrue(module["module"])
                self.assertTrue(module["layer"])
                self.assertTrue(module["target_package"])
                self.assertGreaterEqual(module["loc"], 1)
                self.assertGreaterEqual(module["function_count"], 0)
                self.assertGreaterEqual(module["class_count"], 0)
                self.assertGreaterEqual(module["branch_count"], 0)

    def test_every_observed_fingerprint_has_one_complete_exemption(self) -> None:
        violations = self.inventory["violations"]
        exceptions = self.exemptions["exceptions"]
        observed_ids = [str(item["id"]) for item in violations]
        registered_ids = [str(item["id"]) for item in exceptions]

        self.assertEqual(549, self.inventory["violation_count"])
        self.assertEqual(self.inventory["violation_count"], len(violations))
        self.assertEqual(len(violations), len(exceptions))
        self.assertEqual(len(observed_ids), len(set(observed_ids)))
        self.assertEqual(len(registered_ids), len(set(registered_ids)))
        self.assertEqual(set(observed_ids), set(registered_ids))

        for row in exceptions:
            with self.subTest(exception=row["id"]):
                self.assertEqual(set(), REQUIRED_EXCEPTION_FIELDS - set(row))
                self.assertTrue(str(row["owner"]).strip())
                self.assertTrue(str(row["reason"]).strip())
                self.assertTrue(str(row["replacement"]).strip())
                self.assertTrue(str(row["removal_condition"]).strip())
                self.assertEqual(
                    "tests/test_package_architecture_inventory.py",
                    row["regression_test"],
                )
                self.assertTrue(str(row["issue"]).startswith("#"))
                self.assertIsInstance(row["consumers"], list)
                self.assertTrue(row["consumers"])

    def test_baseline_covers_all_declared_debt_families(self) -> None:
        counts = Counter(
            str(item["category"])
            for item in self.inventory["violations"]
        )
        self.assertEqual(EXPECTED_CATEGORIES, set(counts))
        self.assertEqual(self.inventory["violation_counts"], dict(sorted(counts.items())))
        self.assertGreater(counts["sql-outside-persistence"], 0)
        self.assertGreater(counts["database-acquire-outside-persistence"], 0)
        self.assertGreater(counts["foreign-assignment"], 0)
        self.assertGreater(counts["installer-like-module"], 0)
        self.assertGreater(counts["typing-any-usage"], 0)

        issues = {str(item["issue"]) for item in self.exemptions["exceptions"]}
        self.assertEqual(EXPECTED_BURN_DOWN_ISSUES, issues)
        self.assertEqual("#460", self.exemptions["baseline_issue"])

    def test_shared_private_and_duplicate_fingerprints_are_linked(self) -> None:
        shared = self.inventory["shared_contract_summary"]
        self.assertEqual(639, shared["production_python_files"])
        self.assertEqual(3_660, shared["function_count"])
        self.assertEqual(186, shared["private_contract_access_count"])
        self.assertEqual(0, shared["blocking_private_contract_access_count"])
        self.assertEqual(64, shared["exact_duplicate_group_count"])
        self.assertEqual(98, shared["normalized_duplicate_group_count"])
        self.assertEqual(9, shared["semantic_near_duplicate_group_count"])
        self.assertEqual(
            shared["private_access_sha256"],
            self.exemptions["shared_private_access_sha256"],
        )
        self.assertEqual(
            self.inventory["root_module_sha256"],
            self.exemptions["root_module_sha256"],
        )

    def test_installer_graph_preserves_order_and_patch_evidence(self) -> None:
        graph = self.inventory["installer_graph"]
        self.assertEqual(list(range(1, 29)), [item["order"] for item in graph])
        self.assertEqual("install_runtime_stability", graph[0]["call"])
        self.assertEqual("install_auf_branding", graph[-1]["call"])
        self.assertTrue(any(item["patched_symbols"] for item in graph))
        self.assertTrue(
            any(
                "KieGenerationWorker" in symbol
                or "deliver" in symbol.casefold()
                for item in graph
                for symbol in item["patched_symbols"]
            )
        )

    def test_human_inventory_and_temporary_generator_contract(self) -> None:
        self.assertIn("Production modules: **639**", self.markdown)
        self.assertIn("Production LOC: **138918**", self.markdown)
        self.assertIn("Startup installer stages: **28**", self.markdown)
        self.assertIn("Registered package violations: **549**", self.markdown)
        self.assertIn("Registered exemptions: **549**", self.markdown)
        self.assertIn("Every observed file/category fingerprint", self.markdown)
        self.assertFalse(PREVIEW_WORKFLOW.exists())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs/development_status.md"
MEMORY = ROOT / "docs/project_memory.md"
AUDIT = ROOT / "docs/ARCHITECTURE_AUDIT.md"
CHANGELOG = ROOT / "CHANGELOG.md"
ARCHITECTURE_INVENTORY = ROOT / "docs/architecture_layout_inventory.json"
REPOSITORY_INVENTORY = ROOT / "docs/repository_layout_inventory.json"
SHARED_INVENTORY = ROOT / "docs/shared_contract_inventory.json"
NAVIGATION_INVENTORY = ROOT / "docs/generated/telegram_navigation_inventory.md"


class CanonicalDocsSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.status = STATUS.read_text(encoding="utf-8")
        cls.memory = MEMORY.read_text(encoding="utf-8")
        cls.audit = AUDIT.read_text(encoding="utf-8")
        cls.changelog = CHANGELOG.read_text(encoding="utf-8")
        cls.architecture = json.loads(
            ARCHITECTURE_INVENTORY.read_text(encoding="utf-8")
        )
        cls.repositories = json.loads(
            REPOSITORY_INVENTORY.read_text(encoding="utf-8")
        )
        cls.shared = json.loads(SHARED_INVENTORY.read_text(encoding="utf-8"))
        cls.navigation = NAVIGATION_INVENTORY.read_text(encoding="utf-8")

    def test_canonical_documents_are_dated_and_keep_release_contract(self) -> None:
        for document in (self.status, self.memory, self.audit):
            self.assertIn("30 июля 2026 года", document)
            self.assertNotIn("Дата актуализации: 21 июля 2026 года", document)

        self.assertIn("Текущая стабильная версия: `1.3.0`.", self.status)
        self.assertIn("## [1.3.0] - 2026-07-17", self.changelog)
        self.assertIn("# Линия C. Исторический план раннего рефакторинга", self.memory)
        self.assertIn("# Линия D. Стабильность P2", self.memory)
        self.assertIn("# Линия E. Организация структуры P3", self.memory)

    def test_status_and_audit_match_generated_architecture_counts(self) -> None:
        active_routers = int(self.architecture["active_bundle_router_count"])
        root_modules = int(self.architecture["root_level_module_count"])
        compatibility = int(
            self.architecture["active_compatibility_component_count"]
        )
        repository_modules = int(self.repositories["repository_module_count"])
        domain_repositories = int(self.repositories["layout_counts"]["domain"])
        infrastructure_repositories = int(
            self.repositories["layout_counts"]["infrastructure"]
        )

        required = (
            str(active_routers),
            str(root_modules),
            str(compatibility),
            str(repository_modules),
            str(domain_repositories),
            str(infrastructure_repositories),
        )
        for value in required:
            self.assertIn(value, self.status)
            self.assertIn(value, self.audit)

        self.assertIn("84 active Router imports", self.memory)
        self.assertIn("repository modules: 35", self.memory)
        self.assertNotIn("60 активных routers", self.status)
        self.assertNotIn("30 domain repositories", self.audit)

    def test_shared_contract_baseline_is_represented_without_false_closure(self) -> None:
        production_files = int(self.shared["production_python_files"])
        functions = int(self.shared["function_count"])
        private_debt = int(self.shared["private_contract_access_count"])
        blocking = int(self.shared["blocking_private_contract_access_count"])

        for document in (self.status, self.memory, self.audit):
            self.assertIn(str(production_files), document)
            self.assertIn(str(functions), document)
            self.assertIn(str(private_debt), document)
            self.assertIn(str(blocking), document)
            self.assertIn("#457", document)

        self.assertIn("136 registered transitional private accesses", self.changelog)
        self.assertIn("0 blocking known contracts", self.changelog)
        self.assertIn("transitional", self.audit.casefold())

    def test_live_obligations_and_temporary_layers_are_not_marked_complete(self) -> None:
        for document in (self.status, self.memory, self.audit):
            self.assertIn("#409", document)
            self.assertIn("#410", document)
            self.assertIn("#412", document)
            self.assertIn("#455", document)
            self.assertIn("#457", document)
            self.assertIn("#438", document)
            self.assertIn("meow_*", document)

        self.assertIn("27 side-effect installation stages", self.audit)
        self.assertIn("PR #450/#456", self.audit)
        self.assertIn("временной stabilization", self.status)
        self.assertIn("не закрывается зелёным CI", self.audit)

    def test_navigation_and_branch_maintenance_status_are_current(self) -> None:
        self.assertIn("Python files scanned: **621**", self.navigation)
        self.assertIn("Buttons: **1039**", self.navigation)
        self.assertIn("Violations: **0**", self.navigation)

        for document in (self.status, self.memory, self.audit, self.changelog):
            self.assertIn("branch maintenance", document.casefold())
        self.assertIn("PR #475", self.audit)
        self.assertIn("#461", self.audit)

    def test_changelog_contains_only_current_merged_architecture_story(self) -> None:
        self.assertIn("## [Unreleased]", self.changelog)
        self.assertIn("Ауф: генерации, экономика и пользователи", self.changelog)
        self.assertIn("Safe branch maintenance", self.changelog)
        self.assertIn("84 active imports", self.changelog)
        self.assertIn("34 domain repositories", self.changelog)
        self.assertNotIn("technical runner-PR #444", self.changelog)
        self.assertNotIn("60 active routers", self.changelog)


if __name__ == "__main__":
    unittest.main()

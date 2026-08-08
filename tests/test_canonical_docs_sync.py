from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CanonicalDocsSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.status = (ROOT / "docs/PROJECT_STATUS.md").read_text(encoding="utf-8")
        cls.memory = (ROOT / "docs/PROJECT_MEMORY.md").read_text(encoding="utf-8")
        cls.audit = (ROOT / "docs/P2_AUDIT_REPORT.md").read_text(encoding="utf-8")
        cls.changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        cls.navigation = (
            ROOT / "docs/generated/telegram_navigation_inventory.md"
        ).read_text(encoding="utf-8")
        cls.package_inventory = json.loads(
            (ROOT / "docs/package_architecture_inventory.json").read_text(
                encoding="utf-8"
            )
        )

    def test_canonical_architecture_numbers_match_generated_inventory(self) -> None:
        modules = self.package_inventory["production_module_count"]
        loc = self.package_inventory["production_loc"]
        routers = self.package_inventory["router_count"]
        repositories = self.package_inventory["repository_module_count"]
        installers = len(self.package_inventory["installer_graph"])

        for document in (self.status, self.memory, self.audit):
            self.assertIn(f"{modules}", document)
            self.assertIn(f"{loc}", document)
            self.assertIn(f"{routers}", document)
            self.assertIn(f"{repositories}", document)
            self.assertIn(f"{installers}", document)

    def test_canonical_documents_are_dated_and_keep_release_contract(self) -> None:
        self.assertIn("2026-08-06", self.status)
        self.assertIn("2026-08-06", self.memory)
        self.assertIn("2026-08-06", self.audit)
        self.assertIn("release/reconcile", self.status.casefold())
        self.assertIn("release/reconcile", self.memory.casefold())
        self.assertIn("release/reconcile", self.audit.casefold())
        self.assertIn("current/main", self.status.casefold())
        self.assertIn("current/main", self.memory.casefold())
        self.assertIn("current/main", self.audit.casefold())

    def test_live_obligations_and_temporary_layers_are_not_marked_complete(self) -> None:
        for document in (self.status, self.memory, self.audit):
            self.assertIn("#409", document)
            self.assertIn("#410", document)
            self.assertIn("#412", document)
            self.assertIn("#455", document)
            self.assertIn("#457", document)
            self.assertIn("#438", document)
            self.assertIn("meow_*", document)

        self.assertIn("28 side-effect installation stages", self.audit)
        self.assertIn("PR #450/#456", self.audit)
        self.assertIn("временной stabilization", self.status)
        self.assertIn("не закрывается зелёным CI", self.audit)

    def test_navigation_and_branch_maintenance_status_are_current(self) -> None:
        production_files = self.package_inventory["production_module_count"]
        self.assertIn(
            f"Python files scanned: **{production_files}**",
            self.navigation,
        )
        self.assertIn("Files with buttons: **104**", self.navigation)
        self.assertIn("Buttons: **1065**", self.navigation)
        self.assertIn("Inline buttons: **1061**", self.navigation)
        self.assertIn("Reply buttons: **4**", self.navigation)
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

from __future__ import annotations

import json
import unittest
from pathlib import Path


class CanonicalDocsSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.status = (cls.root / "docs/development_status.md").read_text(
            encoding="utf-8"
        )
        cls.memory = (cls.root / "docs/project_memory.md").read_text(
            encoding="utf-8"
        )
        cls.audit = (cls.root / "docs/ARCHITECTURE_AUDIT.md").read_text(
            encoding="utf-8"
        )
        cls.changelog = (cls.root / "CHANGELOG.md").read_text(encoding="utf-8")
        cls.navigation = (
            cls.root / "docs/generated/telegram_navigation_inventory.md"
        ).read_text(encoding="utf-8")
        cls.package_inventory = json.loads(
            (cls.root / "docs/package_architecture_inventory.json").read_text(
                encoding="utf-8"
            )
        )
        cls.package_exemptions = json.loads(
            (cls.root / "docs/package_architecture_exemptions.json").read_text(
                encoding="utf-8"
            )
        )

    def test_canonical_documents_are_dated_and_keep_release_contract(self) -> None:
        for document in (self.status, self.memory, self.audit):
            self.assertIn("2026-08-05", document)
        self.assertIn("v1.3.0", self.status)
        self.assertIn("v1.3.0", self.memory)
        self.assertIn("v1.3.0", self.audit)
        self.assertIn("1.3.0", self.changelog)

    def test_canonical_architecture_numbers_match_generated_inventory(self) -> None:
        production_files = self.package_inventory["production_module_count"]
        functions = self.package_inventory["shared_contract_summary"][
            "function_count"
        ]
        private_debt = self.package_inventory["shared_contract_summary"][
            "private_contract_access_count"
        ]
        blocking = sum(
            1
            for row in self.package_exemptions["exceptions"]
            if row.get("blocking") is True
        )

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
        self.assertIn("Files with buttons: **106**", self.navigation)
        self.assertIn("Buttons: **1067**", self.navigation)
        self.assertIn("Inline buttons: **1063**", self.navigation)
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

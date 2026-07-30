from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceGuidedNavigationContractTests(unittest.TestCase):
    def test_home_has_a_button_to_resume_the_existing_setup_wizard(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_owner_controls.py"
        ).read_text(encoding="utf-8")

        self.assertIn('text="🧭 Настройка и гид"', source)
        self.assertIn('action="intro"', source)

    def test_every_enabled_workspace_module_has_an_honest_entry_contract(self) -> None:
        publication = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_publications.py"
        ).read_text(encoding="utf-8")
        analytics = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_analytics.py"
        ).read_text(encoding="utf-8")
        ui = (ROOT / "velvet_bot/workspace_ui.py").read_text(encoding="utf-8")

        self.assertIn('module_key == "publications"', publication)
        self.assertIn("PersonalPublicationWorkspaceFilter()", publication)
        self.assertIn('module_key == "analytics"', analytics)
        self.assertIn("PersonalAnalyticsWorkspaceFilter()", analytics)
        self.assertIn("Полный Quality Center", ui)

    def test_personal_routers_precede_generic_workspace_callback_router(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")

        generic = source.index("router.include_router(workspaces_router)")
        self.assertLess(
            source.index("router.include_router(workspace_publication_entry_router)"),
            generic,
        )


if __name__ == "__main__":
    unittest.main()

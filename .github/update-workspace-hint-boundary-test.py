from pathlib import Path

path = Path("tests/test_workspace_hint_preference_boundary.py")
text = path.read_text(encoding="utf-8")
old = '''    def test_telegram_controller_has_no_hint_sql_or_private_repository_access(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
            "workspace_product_experience.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("SELECT show_button_hints", source)
        self.assertNotIn("UPDATE workspace_settings", source)
        self.assertNotIn("workspace_product_service._workspaces", source)
        self.assertNotIn("_database_from_product_service", source)
        self.assertIn("workspace_product_service.get_button_hints", source)
        self.assertIn("workspace_product_service.toggle_button_hints", source)
'''
new = '''    def test_workspace_presentation_has_no_hint_sql_or_private_repository_access(self) -> None:
        controller_source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/core_operations_controllers/"
            "workspace_product_experience.py"
        ).read_text(encoding="utf-8")
        home_source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/"
            "workspace_owner_controls.py"
        ).read_text(encoding="utf-8")

        for source in (controller_source, home_source):
            self.assertNotIn("SELECT show_button_hints", source)
            self.assertNotIn("UPDATE workspace_settings", source)
            self.assertNotIn("workspace_product_service._workspaces", source)
            self.assertNotIn("_database_from_product_service", source)
        self.assertIn(
            "workspace_product_service.get_button_hints",
            home_source,
        )
        self.assertIn(
            "workspace_product_service.toggle_button_hints",
            controller_source,
        )
'''
if text.count(old) != 1:
    raise RuntimeError("Hint boundary test block not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")

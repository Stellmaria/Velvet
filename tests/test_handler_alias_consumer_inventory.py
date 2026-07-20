from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path("scripts/inventory_handler_alias_consumers.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("handler_alias_inventory", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HandlerAliasConsumerInventoryTests(unittest.TestCase):
    def test_inventory_matches_current_tree(self) -> None:
        subprocess.run(
            [
                sys.executable,
                "scripts/inventory_handler_alias_consumers.py",
                "--check",
                "--label",
                "p3d-zero-reference-alias-retirement",
            ],
            check=True,
        )

    def test_inventory_has_no_references_to_missing_aliases(self) -> None:
        data = _load_module().build_inventory(label="test")
        self.assertEqual(data["missing_alias_reference_count"], 0)

    def test_archive_and_reference_alias_group_is_retired(self) -> None:
        retired = {
            "admin_large_media_preview",
            "admin_media_display",
            "admin_media_spoiler",
            "archive",
            "discussion_updates",
            "guest_archive",
            "inline_help",
            "media_browser",
            "media_prompt_binding",
            "public_archive",
            "public_manager",
            "public_media_display",
            "public_notification_open",
            "spoiler_save",
            "start",
            "telegram_analytics_import",
            "reference_albums",
            "reference_comparison",
            "reference_comparison_help",
            "reference_documents",
            "reference_management",
            "references",
        }
        for name in retired:
            with self.subTest(alias=name):
                self.assertFalse(Path("velvet_bot/handlers", f"{name}.py").exists())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
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
                "p3d-supervisor-alias-retirement",
            ],
            check=True,
        )

    def test_inventory_has_no_references_to_missing_aliases(self) -> None:
        data = _load_module().build_inventory(label="test")
        self.assertEqual(data["missing_alias_reference_count"], 0)

    def test_runtime_worktrees_are_not_scanned(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handlers = root / "velvet_bot" / "handlers"
            handlers.mkdir(parents=True)
            (root / "tracked.py").write_text("value = 1\n", encoding="utf-8")
            stale = root / "runtime" / "supervisor" / "codex-worktrees" / "old"
            stale.mkdir(parents=True)
            (stale / "stale_test.py").write_text(
                "import velvet_bot.handlers.removed_alias\n",
                encoding="utf-8",
            )

            original_root = module.ROOT
            original_handlers = module.HANDLERS
            try:
                module.ROOT = root
                module.HANDLERS = handlers
                candidates = module._candidate_paths()
            finally:
                module.ROOT = original_root
                module.HANDLERS = original_handlers

        relative = {path.relative_to(root).as_posix() for path in candidates}
        self.assertEqual(relative, {"tracked.py"})

    def test_retired_alias_groups_are_absent(self) -> None:
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
            "quality_ai",
            "quality_ai_preview",
            "quality_center",
            "quality_duplicates",
            "quality_operations",
            "quality_set_ai",
            "quality_sets",
            "velvet_ai",
            "velvet_ai_formatting",
            "velvet_ai_visual",
            "error_center",
            "owner_actions",
            "owner_menu",
            "publication_center",
            "publication_center_safe",
            "system_center",
            "watermark",
            "backup_center",
            "supervisor_control",
            "supervisor_status",
            "supervisor_process",
            "supervisor_git",
            "supervisor_logs",
            "supervisor_console",
            "supervisor_self",
            "supervisor_codex",
        }
        for name in retired:
            with self.subTest(alias=name):
                self.assertFalse(Path("velvet_bot/handlers", f"{name}.py").exists())


if __name__ == "__main__":
    unittest.main()

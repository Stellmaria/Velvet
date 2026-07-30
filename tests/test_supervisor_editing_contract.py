from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

import velvet_bot.presentation.telegram.supervisor.editing as supervisor_editing

ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR_ROUTERS = (
    ROOT / "velvet_bot" / "presentation" / "telegram" / "routers" / "supervisor"
)
INVENTORY_SCRIPT = ROOT / "scripts" / "inventory_telegram_helpers.py"


class SupervisorEditingContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_editor_delegates_to_canonical_safe_edit(self) -> None:
        message = object()
        keyboard = object()
        original = supervisor_editing.safe_edit_message_text
        replacement = AsyncMock(return_value=True)
        supervisor_editing.safe_edit_message_text = replacement
        try:
            await supervisor_editing.edit_supervisor_message(
                message,  # type: ignore[arg-type]
                "status",
                keyboard,  # type: ignore[arg-type]
            )
        finally:
            supervisor_editing.safe_edit_message_text = original

        replacement.assert_awaited_once_with(
            message,
            "status",
            reply_markup=keyboard,
        )

    async def test_supervisor_routers_do_not_import_private_editor_from_views(self) -> None:
        violations: list[str] = []
        public_consumers: set[str] = set()

        for path in sorted(SUPERVISOR_ROUTERS.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                if node.module == "velvet_bot.presentation.telegram.supervisor.views":
                    for alias in node.names:
                        if alias.name == "_safe_edit":
                            violations.append(f"{path.name}:{node.lineno}")
                if node.module == "velvet_bot.presentation.telegram.supervisor.editing":
                    if any(alias.name == "edit_supervisor_message" for alias in node.names):
                        public_consumers.add(path.name)

        self.assertEqual(violations, [])
        self.assertEqual(
            public_consumers,
            {
                "codex.py",
                "console.py",
                "git.py",
                "logs.py",
                "process.py",
                "self_control.py",
                "status.py",
            },
        )

    async def test_emit_inventory_artifact_for_versioned_refresh(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(INVENTORY_SCRIPT), "--json"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        print("SHARED_CONTRACT_INVENTORY_BEGIN")
        print(completed.stdout)
        print("SHARED_CONTRACT_INVENTORY_END")


if __name__ == "__main__":
    unittest.main()

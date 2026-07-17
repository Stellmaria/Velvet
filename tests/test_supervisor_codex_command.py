from __future__ import annotations

import unittest
from pathlib import Path

from velvet_supervisor.codex_command import normalize_codex_command


class SupervisorCodexCommandTests(unittest.TestCase):
    def test_non_windows_command_is_unchanged(self) -> None:
        command = ("codex", "exec", "--json", "-")

        normalized = normalize_codex_command(command, is_windows=False)

        self.assertEqual(command, normalized)

    def test_powershell_npm_shim_uses_sibling_cmd_wrapper(self) -> None:
        command = (
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "C:/Users/test/AppData/Roaming/npm/codex.ps1",
            "exec",
            "--json",
            "--sandbox",
            "workspace-write",
            "-",
        )

        normalized = normalize_codex_command(
            command,
            is_windows=True,
            path_exists=lambda path: path == Path(
                "C:/Users/test/AppData/Roaming/npm/codex.cmd"
            ),
        )

        self.assertEqual(("cmd.exe", "/d", "/s", "/c"), normalized[:4])
        self.assertIn("chcp 65001", normalized[4])
        self.assertIn("codex.cmd", normalized[4])
        self.assertIn("exec --json --sandbox workspace-write -", normalized[4])
        self.assertNotIn("codex.ps1", normalized[4])

    def test_bare_codex_resolved_to_npm_cmd_is_wrapped(self) -> None:
        normalized = normalize_codex_command(
            ("codex", "exec", "-"),
            is_windows=True,
            which=lambda _name: "C:/Users/test/AppData/Roaming/npm/codex.CMD",
        )

        self.assertEqual(("cmd.exe", "/d", "/s", "/c"), normalized[:4])
        self.assertIn("codex.CMD", normalized[4])
        self.assertTrue(normalized[4].endswith("exec -"))

    def test_unrelated_powershell_script_is_not_rewritten(self) -> None:
        command = (
            "powershell.exe",
            "-File",
            "C:/tools/other.ps1",
            "-",
        )

        normalized = normalize_codex_command(
            command,
            is_windows=True,
            path_exists=lambda _path: True,
        )

        self.assertEqual(command, normalized)


if __name__ == "__main__":
    unittest.main()

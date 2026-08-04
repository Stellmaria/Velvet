from __future__ import annotations

import importlib.util
import stat
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path("deploy/hermes-coders/ensure_runtime_config.py")
SPEC = importlib.util.spec_from_file_location("ensure_runtime_config", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Не удалось загрузить {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class HermesRuntimeConfigTests(unittest.TestCase):
    def write_config(self, body: str, mode: int = 0o640) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "config.yaml"
        path.write_text(body, encoding="utf-8")
        path.chmod(mode)
        return path

    def test_adds_passthrough_to_existing_terminal_section(self) -> None:
        path = self.write_config(
            "model:\n"
            "  default: gpt-5.4-mini\n"
            "terminal:\n"
            "  cwd: /workspace\n"
            "display:\n"
            "  tool_progress_command: true\n"
        )

        changed = MODULE.ensure_env_passthrough(path)
        text = path.read_text(encoding="utf-8")

        self.assertTrue(changed)
        self.assertTrue(MODULE.config_has_env_passthrough(text, "GH_TOKEN"))
        self.assertLess(text.index("terminal:"), text.index("env_passthrough:"))
        self.assertLess(text.index("env_passthrough:"), text.index("display:"))

    def test_preserves_existing_passthrough_and_is_idempotent(self) -> None:
        path = self.write_config(
            "terminal:\n"
            "  cwd: /workspace\n"
            "  env_passthrough:\n"
            "    - EXISTING_TOKEN\n"
        )

        first = MODULE.ensure_env_passthrough(path)
        first_text = path.read_text(encoding="utf-8")
        second = MODULE.ensure_env_passthrough(path)
        second_text = path.read_text(encoding="utf-8")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertIn("- EXISTING_TOKEN", first_text)
        self.assertEqual(1, first_text.count("GH_TOKEN"))
        self.assertEqual(first_text, second_text)

    def test_updates_empty_inline_passthrough(self) -> None:
        path = self.write_config(
            "terminal:\n"
            "  cwd: /workspace\n"
            "  env_passthrough: []\n"
        )

        MODULE.ensure_env_passthrough(path)
        text = path.read_text(encoding="utf-8")

        self.assertIn("env_passthrough: [GH_TOKEN]", text)
        self.assertTrue(MODULE.config_has_env_passthrough(text, "GH_TOKEN"))

    def test_appends_terminal_section_when_missing(self) -> None:
        path = self.write_config("model:\n  default: gpt-5.4-mini\n")

        MODULE.ensure_env_passthrough(path)
        text = path.read_text(encoding="utf-8")

        self.assertIn("terminal:\n  env_passthrough:\n    - GH_TOKEN\n", text)

    def test_preserves_file_mode(self) -> None:
        path = self.write_config(
            "terminal:\n  cwd: /workspace\n",
            mode=0o600,
        )

        MODULE.ensure_env_passthrough(path)

        self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))

    def test_rejects_unsupported_scalar(self) -> None:
        path = self.write_config(
            "terminal:\n"
            "  cwd: /workspace\n"
            "  env_passthrough: GH_TOKEN\n"
        )

        with self.assertRaises(MODULE.ConfigPatchError):
            MODULE.ensure_env_passthrough(path)

    def test_coder_profile_adds_context_and_gateway_guardrails(self) -> None:
        path = self.write_config("model:\n  default: gpt-5.4-mini\n")

        first = MODULE.ensure_runtime_contract(path, profile="coder")
        text = path.read_text(encoding="utf-8")
        second = MODULE.ensure_runtime_contract(path, profile="coder")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertTrue(
            MODULE.config_has_mapping_scalar(text, "terminal", "cwd", "/workspace")
        )
        self.assertTrue(
            MODULE.config_has_mapping_scalar(text, "compression", "enabled", "true")
        )
        self.assertTrue(
            MODULE.config_has_mapping_scalar(
                text,
                "tool_loop_guardrails",
                "hard_stop_enabled",
                "true",
            )
        )
        self.assertTrue(MODULE.config_has_env_passthrough(text, "GH_TOKEN"))
        self.assertFalse(
            MODULE.config_has_sequence_item(
                text,
                "plugins",
                "enabled",
                MODULE.KAEL_CODER_CONTROL_PLUGIN,
            )
        )

    def test_kael_profile_uses_data_cwd_and_enables_coder_control(self) -> None:
        path = self.write_config(
            "terminal:\n"
            "  backend: local\n"
            "plugins:\n"
            "  enabled: []\n"
        )

        first = MODULE.ensure_runtime_contract(path, profile="kael")
        text = path.read_text(encoding="utf-8")
        second = MODULE.ensure_runtime_contract(path, profile="kael")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertTrue(
            MODULE.config_has_mapping_scalar(text, "terminal", "cwd", "/opt/data")
        )
        self.assertFalse(MODULE.config_has_env_passthrough(text, "GH_TOKEN"))
        self.assertTrue(
            MODULE.config_has_mapping_scalar(
                text,
                "tool_loop_guardrails",
                "warnings_enabled",
                "true",
            )
        )
        self.assertTrue(
            MODULE.config_has_sequence_item(
                text,
                "plugins",
                "enabled",
                MODULE.KAEL_CODER_CONTROL_PLUGIN,
            )
        )
        self.assertEqual(1, text.count(MODULE.KAEL_CODER_CONTROL_PLUGIN))

    def test_kael_profile_preserves_existing_enabled_plugins(self) -> None:
        path = self.write_config(
            "plugins:\n"
            "  enabled:\n"
            "    - existing-plugin\n"
        )

        MODULE.ensure_runtime_contract(path, profile="kael")
        text = path.read_text(encoding="utf-8")

        self.assertIn("- existing-plugin", text)
        self.assertIn(f"- {MODULE.KAEL_CODER_CONTROL_PLUGIN}", text)

    def test_kael_profile_adds_plugins_section_when_missing(self) -> None:
        path = self.write_config("model:\n  default: gpt-5.4-mini\n")

        MODULE.ensure_runtime_contract(path, profile="kael")
        text = path.read_text(encoding="utf-8")

        self.assertIn(
            "plugins:\n  enabled:\n    - kael-coder-control\n",
            text,
        )


if __name__ == "__main__":
    unittest.main()

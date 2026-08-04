from __future__ import annotations

import ast
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "deploy/hermes-operator/plugins/kael-coder-control"


class KaelCoderControlDeploymentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = (PLUGIN_ROOT / "__init__.py").read_text(encoding="utf-8")
        self.manifest = (PLUGIN_ROOT / "plugin.yaml").read_text(encoding="utf-8")
        self.operator_installer = (
            ROOT / "deploy/hermes-operator/install.sh"
        ).read_text(encoding="utf-8")
        self.entities_reconcile = (
            ROOT / "deploy/hermes-entities/reconcile.sh"
        ).read_text(encoding="utf-8")
        self.agents = (
            ROOT / "deploy/hermes-operator/AGENTS.kael.md"
        ).read_text(encoding="utf-8")
        self.plugin_tests = (
            ROOT / "tests/test_hermes_kael_coder_control.py"
        ).read_text(encoding="utf-8")

    def test_plugin_manifest_declares_typed_tool_and_policy_hooks(self) -> None:
        self.assertIn("name: kael-coder-control", self.manifest)
        self.assertIn("- coder_delegate", self.manifest)
        self.assertIn("- pre_tool_call", self.manifest)
        self.assertIn("- post_tool_call", self.manifest)

    def test_plugin_uses_argv_without_shell_interpolation(self) -> None:
        tree = ast.parse(self.plugin)
        self.assertIsNotNone(tree)
        self.assertIn("subprocess.run(", self.plugin)
        self.assertIn("shell=False", self.plugin)
        self.assertNotIn("shell=True", self.plugin)
        self.assertNotIn("os.system", self.plugin)
        self.assertIn('"production_privileges": False', self.plugin)

    def test_operator_installer_places_and_enables_user_plugin(self) -> None:
        for marker in (
            'KAEL_CODER_PLUGIN_SOURCE="$SOURCE_DIR/plugins/kael-coder-control"',
            'kael_plugin_target="$hermes_data/plugins/kael-coder-control"',
            '"$kael_plugin_target/plugin.yaml"',
            '"$kael_plugin_target/__init__.py"',
            '"$hermes_data/audit"',
            'python3 "$RUNTIME_CONFIG_PATCHER"',
            "--profile kael",
        ):
            self.assertIn(marker, self.operator_installer)
        self.assertIn("install -m 0640", self.operator_installer)

    def test_entities_reconcile_repairs_plugin_and_audit_contract(self) -> None:
        for marker in (
            'KAEL_CODER_PLUGIN_SOURCE="$OPERATOR_SOURCE/plugins/kael-coder-control"',
            'kael_plugin_target="$hermes_data/plugins/kael-coder-control"',
            '"$kael_plugin_target/plugin.yaml"',
            '"$kael_plugin_target/__init__.py"',
            '"$hermes_data/audit"',
            "--profile kael",
        ):
            self.assertIn(marker, self.entities_reconcile)
        self.assertIn("install -m 0640", self.entities_reconcile)

    def test_kael_instructions_require_typed_submit_and_preserve_control(self) -> None:
        self.assertIn("typed tool `coder_delegate`", self.agents)
        self.assertIn("Локальный fallback запрещён", self.agents)
        self.assertNotIn("coderctl.py submit velvet", self.agents)
        self.assertNotIn("coderctl.py submit max", self.agents)
        for controller in (
            "opsctl.py",
            "monitorctl.py",
            "reconcilectl.py",
            "runctl.py",
        ):
            self.assertIn(controller, self.agents)
        self.assertIn('tool_name="delegate_task"', self.plugin_tests)

    def test_shell_deployment_files_parse(self) -> None:
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("bash is unavailable")
        for relative in (
            "deploy/hermes-operator/install.sh",
            "deploy/hermes-entities/reconcile.sh",
        ):
            result = subprocess.run(
                [bash, "-n", str(ROOT / relative)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, f"{relative}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()

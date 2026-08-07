from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
OPERATOR_DIR = ROOT / "deploy/hermes-operator"
sys.path.insert(0, str(OPERATOR_DIR))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


coderctl = load_module("kael_ledger_hotfix_coderctl", OPERATOR_DIR / "coderctl.py")


class KaelOrchestrationOwnershipContractTests(unittest.TestCase):
    def test_installer_preserves_main_hermes_owner_for_tools_and_ledger(self) -> None:
        source = (ROOT / "deploy/hermes-orchestration/install.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('hermes_uid="$(stat -c \'%u\' "$hermes_data")"', source)
        self.assertIn('hermes_gid="$(stat -c \'%g\' "$hermes_data")"', source)
        self.assertIn(
            'install -d -o "$hermes_uid" -g "$hermes_gid" -m 0750 \\\n'
            '  "$hermes_data/tools" "$hermes_data/orchestration"',
            source,
        )
        self.assertIn(
            'install -m 0500 -o "$hermes_uid" -g "$hermes_gid" \\\n'
            '  "$OPERATOR_SOURCE/coderctl.py" "$hermes_data/tools/coderctl.py"',
            source,
        )
        self.assertIn(
            'chown "$hermes_uid:$hermes_gid" "$hermes_data/orchestration"',
            source,
        )
        self.assertNotIn('velvet_uid="$(stat -c \'%u\' "$velvet_data_dir")"', source)
        self.assertNotIn('velvet_gid="$(stat -c \'%g\' "$velvet_data_dir")"', source)


class CoderCtlLedgerPreflightTests(unittest.TestCase):
    def test_submit_fails_before_router_when_ledger_is_not_writable(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.object(
            coderctl.Ledger,
            "ensure_writable",
            side_effect=coderctl.CoderApiError("ledger denied"),
        ), patch.object(coderctl.RouterClient, "submit") as submit:
            code = coderctl.main(
                [
                    "--ledger",
                    str(Path(directory) / "tasks.json"),
                    "submit",
                    "velvet",
                    "--task",
                    "Read only canary",
                    "--task-type",
                    "read_only",
                    "--complexity",
                    "small",
                    "--risk",
                    "low",
                    "--mutation-policy",
                    "read_only",
                    "--tier",
                    "small",
                ]
            )
        self.assertEqual(2, code)
        submit.assert_not_called()

    def test_writable_preflight_leaves_no_probe_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = coderctl.Ledger(root / "tasks.json")
            ledger.ensure_writable()
            probes = list(root.glob(".coderctl-write-check-*"))
        self.assertEqual([], probes)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


delegate = load("issue581_delegate", "deploy/hermes-coders/codex_delegate.py")


class Issue581ContractTests(unittest.TestCase):
    def test_canonical_identity_parity_is_velvet_and_max(self) -> None:
        router = load("issue581_router", "deploy/hermes-operator/coder_router.py")
        targets = router.load_targets()
        self.assertEqual("Велвет", targets["velvet"].identity)
        self.assertEqual("Макс", targets["max"].identity)
        self.assertIn("Ты Велвет", (ROOT / "deploy/hermes-coders/SOUL.velvet.md").read_text())
        self.assertIn("Ты Макс", (ROOT / "deploy/hermes-coders/SOUL.max.md").read_text())

    def test_direct_path_uses_central_router_and_owner_source(self) -> None:
        payload = delegate.build_payload(
            "Inspect README", project="velvet", model=None,
            task_type="read_only", complexity="small", risk="low",
            mutation_policy="read_only", requested_tier="small",
        )
        self.assertEqual("owner-direct", payload["source"])
        self.assertRegex(payload["task_id"], r"^[a-f0-9]{32}$")
        self.assertNotIn("input", payload)
        self.assertNotIn("model", payload)
        compose = (ROOT / "deploy/hermes-coders/compose.runtime.yaml").read_text()
        self.assertEqual(2, compose.count("http://hermes-coder-router:8878"))
        source = (ROOT / "deploy/hermes-coders/codex_delegate.py").read_text()
        self.assertIn("HERMES_CODER_ROUTER_CLIENT_TOKEN", source)
        self.assertNotIn('self.token = _required_env("CODEX_RUNNER_API_KEY"', source)
        self.assertNotIn("subprocess", source)

    def test_direct_router_is_fail_closed(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(delegate.DelegateError):
                delegate.RunnerClient()

    def test_security_layer_is_named_and_applies_only_to_runners(self) -> None:
        layer = (ROOT / "deploy/hermes-coders/compose.security.yaml").read_text()
        self.assertIn("hermes-coder-velvet", layer)
        self.assertIn("hermes-coder-max", layer)
        self.assertNotIn("hermes-chat-", layer)
        self.assertEqual(2, layer.count("apparmor=hermes-codex-bwrap"))
        self.assertEqual(2, layer.count("seccomp=./security/seccomp-bwrap.json"))
        seccomp = json.loads(
            (ROOT / "deploy/hermes-coders/security/seccomp-bwrap.json").read_text()
        )
        self.assertEqual("SCMP_ACT_ERRNO", seccomp["defaultAction"])
        allowed = set(seccomp["syscalls"][0]["names"])
        self.assertTrue({"clone", "unshare", "mount", "umount2"} <= allowed)
        self.assertNotIn("ptrace", allowed)

    def test_lifecycle_uses_all_layers_and_restarts_oneshot(self) -> None:
        unit = (ROOT / "deploy/systemd/hermes-coders.service").read_text()
        layers = "-f compose.yaml -f compose.runtime.yaml -f compose.security.yaml"
        self.assertGreaterEqual(unit.count(layers), 4)
        installer = (ROOT / "deploy/hermes-coders/install.sh").read_text()
        self.assertIn("systemctl daemon-reload", installer)
        self.assertIn("systemctl enable hermes-coders.service", installer)
        self.assertIn("systemctl restart hermes-coders.service", installer)
        self.assertIn("-p ActiveState --value", installer)
        self.assertIn("-p SubState --value", installer)
        self.assertIn("-p ExecMainStatus --value", installer)
        self.assertNotIn("enable --now hermes-coders.service", installer)

    def test_both_runners_use_canonical_entrypoint_and_sandbox_smoke(self) -> None:
        runtime = (ROOT / "deploy/hermes-coders/compose.runtime.yaml").read_text()
        self.assertEqual(2, runtime.count("- /app/codex_tier_runner.py"))
        smoke = (ROOT / "deploy/hermes-coders/runtime_smoke.py").read_text()
        for marker in (
            "unshare --user --map-root-user true",
            "unshare --user --map-root-user --mount true", "bwrap --unshare-user",
            "fingerprint_before", "hermes-codex-bwrap", "Seccomp", "NoNewPrivs",
            'CRYPTOGRAPHY_VERSION = "50.0.0"',
        ):
            self.assertIn(marker, smoke)
        tier_runner = (ROOT / "deploy/hermes-coders/codex_tier_runner.py").read_text()
        for marker in (
            '"fetch", "--prune", "origin", "main"',
            '"worktree", "add", "--detach"',
            "CODEX_ISOLATED_WORKTREE_ROOT",
            "isolated_workspace_cleanup_failed",
        ):
            self.assertIn(marker, tier_runner)
        self.assertIn("def _worktree_git", tier_runner)
        self.assertNotIn("def _git(self, *args", tier_runner)


if __name__ == "__main__":
    unittest.main()

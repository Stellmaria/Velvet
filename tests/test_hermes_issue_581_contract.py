from __future__ import annotations

import importlib.util
import json
import os
import sys
import subprocess
import tempfile
import shutil
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
        self.assertNotIn("no-new-privileges", layer)
        seccomp = json.loads(
            (ROOT / "deploy/hermes-coders/security/seccomp-bwrap.json").read_text()
        )
        self.assertEqual("SCMP_ACT_ERRNO", seccomp["defaultAction"])
        self.assertEqual(
            "https://github.com/moby/profiles/blob/main/seccomp/default.json",
            seccomp["_baseProfile"],
        )
        added = next(rule for rule in seccomp["syscalls"] if rule.get("comment") == "Hermes bwrap additions")
        self.assertEqual(
            {"mount", "umount2", "pivot_root", "unshare"},
            set(added["names"]),
        )
        clone = next(
            rule for rule in seccomp["syscalls"]
            if rule.get("comment") == "Hermes bwrap user namespace clone"
        )
        self.assertEqual("SCMP_CMP_MASKED_EQ", clone["args"][0]["op"])
        self.assertEqual(268435456, clone["args"][0]["valueTwo"])

    def test_three_layer_compose_config_is_valid(self) -> None:
        if subprocess.run(["docker", "compose", "version"], capture_output=True).returncode:
            self.skipTest("docker compose CLI unavailable")
        source = ROOT / "deploy/hermes-coders"
        with tempfile.TemporaryDirectory() as directory:
            secrets = Path(directory) / "secrets"
            secrets.mkdir()
            for name in ("velvet.env", "velvet-db.env", "max.env", "max-db.env"):
                (secrets / name).touch()
            env = os.environ | {"HERMES_CODERS_ROOT": directory}
            result = subprocess.run(
                ["docker", "compose", "--profile", "velvet", "--profile", "max",
                 "-f", "compose.yaml", "-f", "compose.runtime.yaml",
                 "-f", "compose.security.yaml", "config", "--quiet"],
                cwd=source, env=env, capture_output=True, text=True,
            )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_apparmor_profile_has_bwrap_mount_and_project_exec_rules(self) -> None:
        profile = ROOT / "deploy/hermes-coders/security/apparmor-hermes-codex-bwrap"
        source = profile.read_text(encoding="utf-8")
        for rule in (
            "rslave", "mount options=(rw, bind) / -> /",
            "mount options=(ro, remount, bind) / -> /",
            "mount options=(rw, rbind) /dev -> /dev",
            "mount options=(rw, bind) /workspace -> /workspace",
            "fstype=proc", "pivot_root",
            "/usr/bin/git ix", "/usr/local/bin/** ix",
        ):
            self.assertIn(rule, source)
        parser = shutil.which("apparmor_parser")
        if parser:
            with tempfile.TemporaryDirectory() as cache:
                result = subprocess.run(
                    [parser, "-Q", "--cache-loc", cache, str(profile)],
                    capture_output=True,
                    text=True,
                )
            self.assertEqual(0, result.returncode, result.stderr)

    def test_orchestration_installer_closes_token_context_and_restart_lifecycle(self) -> None:
        source = (ROOT / "deploy/hermes-orchestration/install.sh").read_text(encoding="utf-8")
        self.assertIn('set_value(velvet_path, "HERMES_CODER_ROUTER_CLIENT_TOKEN"', source)
        self.assertIn('set_value(max_path, "HERMES_CODER_ROUTER_CLIENT_TOKEN"', source)
        self.assertIn("compose.runtime.yaml", source)
        self.assertIn("compose.security.yaml", source)
        self.assertNotIn('$CODERS_SOURCE/SOUL.$project.md" "$data_dir/SOUL.md"', source)
        verify = source.rfind("verify_installed_context.py")
        self.assertGreater(verify, source.rfind("install_context_pack.py"))
        self.assertNotIn('relative="${managed_file#', source)
        context_installer = (ROOT / "deploy/hermes-brain/install_context_pack.py").read_text()
        self.assertIn("mode=0o600", context_installer)
        for unit in (
            "systemctl restart hermes-coders.service",
            "systemctl restart hermes-coder-router.service",
            "systemctl restart velvet-hermes-incident-monitor.service",
        ):
            self.assertIn(unit, source)

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
            'CRYPTOGRAPHY_VERSION = "50.0.0"', "docker-compose.server.yml",
            '"hermes", "python"', "--ro-bind / / --dev-bind /dev /dev",
        ):
            self.assertIn(marker, smoke)
        tier_runner = (ROOT / "deploy/hermes-coders/codex_tier_runner.py").read_text()
        for marker in (
            '"remote", "show", "origin"', "default_branch",
            '"worktree", "add", "--detach"',
            "CODEX_ISOLATED_WORKTREE_ROOT",
            "isolated_workspace_cleanup_failed",
        ):
            self.assertIn(marker, tier_runner)
        self.assertIn("def _worktree_git", tier_runner)
        self.assertNotIn("def _git(self, *args", tier_runner)
        self.assertNotIn('"origin/main"', tier_runner)


if __name__ == "__main__":
    unittest.main()

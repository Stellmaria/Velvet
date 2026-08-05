from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path("deploy/hermes-coders/runtime_smoke.py")
SPEC = importlib.util.spec_from_file_location("hermes_runtime_smoke", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
runtime_smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime_smoke
SPEC.loader.exec_module(runtime_smoke)

RELEASE_ROOT = "/srv/hermes-coders/releases/current-hermes-coders"


class HermesCoderRuntimeSmokeTests(unittest.TestCase):
    def test_compose_prefix_is_fixed_and_cwd_independent(self) -> None:
        command = runtime_smoke.compose_prefix()
        self.assertEqual("hermes-coders", command[command.index("--project-name") + 1])
        compose_paths = [
            Path(command[index + 1])
            for index, value in enumerate(command)
            if value == "-f"
        ]
        self.assertEqual(list(runtime_smoke.COMPOSE_FILES), compose_paths)
        self.assertTrue(all(path.is_absolute() for path in compose_paths))

    def test_chat_probe_is_non_mutating_and_checks_push_auth(self) -> None:
        for target in runtime_smoke.CODERS:
            script = runtime_smoke.github_probe_script(target)
            self.assertIn("gh api user", script)
            self.assertIn(".permissions.push", script)
            self.assertIn("gh auth git-credential", script)
            self.assertIn("push --dry-run", script)
            self.assertNotIn("gh pr create", script)
            self.assertNotIn("gh api --method", script)

    def test_coder_probe_checks_canonical_launcher_and_current_main_guards(self) -> None:
        target = runtime_smoke.CODERS[0]
        script = runtime_smoke.codex_probe_script(target)
        for marker in (
            "SandboxLauncherClient",
            "project_auth",
            "client.probe",
            "host-sandbox-launcher",
            "disposable-docker-container",
            "nested_bwrap",
            "gh api repos/Stellmaria/Velvet --jq .default_branch",
            'git check-ref-format --branch "$default_branch"',
            "hermes-codex-runner",
            "test ! -e /workspace",
            "push --dry-run",
        ):
            self.assertIn(marker, script)
        for forbidden in (
            "bwrap --unshare-user",
            "unshare --user",
            "--proc /proc",
        ):
            self.assertNotIn(forbidden, script)

    def test_wait_for_service_retries_then_succeeds(self) -> None:
        calls: list[list[str]] = []
        results = [
            subprocess.CompletedProcess([], 1, "", "not ready"),
            subprocess.CompletedProcess([], 0, "", ""),
        ]
        ticks = iter((0.0, 0.0, 1.0, 1.0, 2.0))

        def runner(args, _timeout):
            calls.append(list(args))
            return results.pop(0)

        runtime_smoke.wait_for_service(
            runtime_smoke.CODERS[0].coder_service,
            timeout_seconds=10,
            poll_seconds=0,
            runner=runner,
            monotonic=lambda: next(ticks),
            sleeper=lambda _seconds: None,
        )
        self.assertEqual(2, len(calls))

    def test_failed_probe_redacts_token(self) -> None:
        def runner(_args, _timeout):
            return subprocess.CompletedProcess([], 1, "", "token=github_pat_secretvalue")

        with self.assertRaises(runtime_smoke.SmokeError) as context:
            runtime_smoke.verify_github_access(runtime_smoke.CODERS[1], runner=runner)
        message = str(context.exception)
        self.assertIn("[REDACTED]", message)
        self.assertNotIn("secretvalue", message)

    def test_systemd_runs_smoke_after_no_build_start_and_reload(self) -> None:
        source = Path("deploy/systemd/hermes-coders.service").read_text(encoding="utf-8")
        prefix = f"{RELEASE_ROOT}/deploy/hermes-coders"
        smoke = f"ExecStartPost=/usr/bin/python3 {prefix}/runtime_smoke.py"
        reload_smoke = f"ExecReload=/usr/bin/python3 {prefix}/runtime_smoke.py"
        self.assertIn(smoke, source)
        self.assertIn(reload_smoke, source)
        self.assertIn("--no-build", source)
        self.assertNotIn("HERMES_CODEX_STRICT_NESTED_PROC_SMOKE", source)
        self.assertNotIn("/srv/velvet/deploy/hermes-coders", source)


if __name__ == "__main__":
    unittest.main()

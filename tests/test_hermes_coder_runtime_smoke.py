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


class HermesCoderRuntimeSmokeTests(unittest.TestCase):
    def test_probe_is_non_mutating_and_checks_real_push_auth(self) -> None:
        for target in runtime_smoke.CODERS:
            with self.subTest(project=target.project):
                script = runtime_smoke.github_probe_script(target)
                self.assertIn(target.repository, script)
                self.assertIn("gh api user", script)
                self.assertIn(".permissions.push", script)
                self.assertIn("gh auth git-credential", script)
                self.assertIn("git -C /workspace push --dry-run", script)
                self.assertIn(f"hermes-auth-smoke-{target.project}", script)
                self.assertNotIn("gh pr create", script)
                self.assertNotIn("gh api --method", script)
                self.assertNotIn("git -C /workspace push origin", script)

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
        self.assertIn("hermes-coder-velvet", calls[0])

    def test_failed_probe_redacts_token(self) -> None:
        def runner(_args, _timeout):
            return subprocess.CompletedProcess(
                [], 1, "", "token=github_pat_secretvalue"
            )

        with self.assertRaises(runtime_smoke.SmokeError) as context:
            runtime_smoke.verify_github_access(
                runtime_smoke.CODERS[1], runner=runner
            )
        message = str(context.exception)
        self.assertIn("[REDACTED]", message)
        self.assertNotIn("secretvalue", message)

    def test_systemd_runs_live_smoke_from_exact_release_link(self) -> None:
        source = Path("deploy/systemd/hermes-coders.service").read_text(
            encoding="utf-8"
        )
        prefix = (
            "/srv/hermes-coders/releases/current-hermes-coders/"
            "deploy/hermes-coders"
        )
        smoke = f"ExecStartPost=/usr/bin/python3 {prefix}/runtime_smoke.py"
        reload_smoke = f"ExecReload=/usr/bin/python3 {prefix}/runtime_smoke.py"
        self.assertIn(f"WorkingDirectory={prefix}", source)
        self.assertIn(smoke, source)
        self.assertIn(reload_smoke, source)
        self.assertNotIn("/srv/velvet/deploy/hermes-coders", source)
        self.assertLess(source.index("ExecStart=/usr/bin/docker"), source.index(smoke))
        self.assertLess(
            source.index("ExecReload=/usr/bin/docker"), source.index(reload_smoke)
        )

    def test_reinstall_preserves_runs_key_and_activates_launcher_first(self) -> None:
        source = Path("deploy/hermes-coders/install.sh").read_text(encoding="utf-8")
        self.assertIn('"API_SERVER_KEY": api_key', source)
        self.assertIn('"CODEX_RUNNER_API_KEY": runner_key', source)
        self.assertIn('"$LAUNCHER_INSTALLER"', source)
        self.assertIn("current-hermes-coders", source)
        self.assertIn("compose.security.yaml", source)
        self.assertLess(source.index('"$LAUNCHER_INSTALLER"'), source.index('"${compose[@]}" build'))
        self.assertLess(source.index('"${compose[@]}" build'), source.index("systemctl restart hermes-coders.service"))
        self.assertNotIn("apparmor-hermes-codex-bwrap", source)
        self.assertNotIn("seccomp-bwrap.json", source)
        self.assertNotIn("compose.bwrap.override.yaml", source)


if __name__ == "__main__":
    unittest.main()

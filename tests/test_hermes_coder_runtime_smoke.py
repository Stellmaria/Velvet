from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path("deploy/hermes-coders/runtime_smoke.py")
SPEC = importlib.util.spec_from_file_location("hermes_runtime_smoke", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
runtime_smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime_smoke
SPEC.loader.exec_module(runtime_smoke)

RELEASE_ROOT = "/srv/hermes-coders/releases/current-hermes-coders"


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

    def test_codex_probe_uses_api_default_branch_and_optional_nested_proc(self) -> None:
        target = runtime_smoke.CODERS[0]
        with patch.object(runtime_smoke, "STRICT_NESTED_PROC_SMOKE", False):
            startup_script = runtime_smoke.codex_probe_script(target)
        self.assertIn("gh api repos/Stellmaria/Velvet --jq .default_branch", startup_script)
        self.assertIn('git check-ref-format --branch "$default_branch"', startup_script)
        self.assertNotIn("git ls-remote --symref", startup_script)
        self.assertNotIn("--proc /proc true", startup_script)
        self.assertIn("nested /proc probe is a separate strict diagnostic", startup_script)

        with patch.object(runtime_smoke, "STRICT_NESTED_PROC_SMOKE", True):
            strict_script = runtime_smoke.codex_probe_script(target)
        self.assertIn(
            "bwrap --unshare-user --unshare-pid --ro-bind / / --proc /proc true",
            strict_script,
        )

    def test_compose_prefix_is_cwd_independent_and_fixed_project(self) -> None:
        command = runtime_smoke.compose_prefix()
        self.assertEqual("hermes-coders", command[command.index("--project-name") + 1])
        compose_paths = [
            Path(command[index + 1])
            for index, value in enumerate(command)
            if value == "-f"
        ]
        self.assertEqual(list(runtime_smoke.COMPOSE_FILES), compose_paths)
        self.assertTrue(all(path.is_absolute() for path in compose_paths))

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
                [],
                1,
                "",
                "token=github_pat_secretvalue",
            )

        with self.assertRaises(runtime_smoke.SmokeError) as context:
            runtime_smoke.verify_github_access(
                runtime_smoke.CODERS[1],
                runner=runner,
            )
        message = str(context.exception)
        self.assertIn("[REDACTED]", message)
        self.assertNotIn("secretvalue", message)

    def test_systemd_runs_release_smoke_after_start_and_reload(self) -> None:
        source = Path("deploy/systemd/hermes-coders.service").read_text(
            encoding="utf-8"
        )
        smoke = (
            "ExecStartPost=/usr/bin/python3 "
            f"{RELEASE_ROOT}/deploy/hermes-coders/runtime_smoke.py"
        )
        reload_smoke = (
            "ExecReload=/usr/bin/python3 "
            f"{RELEASE_ROOT}/deploy/hermes-coders/runtime_smoke.py"
        )
        self.assertIn(smoke, source)
        self.assertIn(reload_smoke, source)
        self.assertIn("HERMES_CODEX_STRICT_NESTED_PROC_SMOKE=0", source)
        self.assertNotIn("/srv/velvet/deploy/hermes-coders", source)
        self.assertLess(source.index("ExecStart=/usr/bin/docker"), source.index(smoke))
        self.assertLess(
            source.index("ExecReload=/usr/bin/docker"), source.index(reload_smoke)
        )

    def test_reinstall_preserves_runs_api_key_and_requires_smoke(self) -> None:
        source = Path("deploy/hermes-coders/install.sh").read_text(encoding="utf-8")
        self.assertIn(
            '"API_SERVER_KEY": existing.get("API_SERVER_KEY", "")',
            source,
        )
        self.assertIn('"$SOURCE_DIR/runtime_smoke.py"', source)
        self.assertIn("python3 $SOURCE_DIR/runtime_smoke.py", source)


if __name__ == "__main__":
    unittest.main()

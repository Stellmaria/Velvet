from __future__ import annotations

import ast
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path("deploy/hermes-coders")
LAUNCHER_ROOT = Path("deploy/hermes-sandbox-launcher")
RELEASE_PREFIX = "/srv/hermes-coders/releases/current-hermes-coders/deploy/hermes-coders"


class HermesCodersContractTests(unittest.TestCase):
    def test_chat_and_codex_services_use_separate_workspaces(self) -> None:
        source = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn("  hermes-chat-velvet:", source)
        self.assertIn("  hermes-chat-max:", source)
        self.assertIn("  hermes-coder-velvet:", source)
        self.assertIn("  hermes-coder-max:", source)
        self.assertIn("/workspaces/velvet:/workspace", source)
        self.assertIn("/workspaces/max:/workspace", source)
        self.assertIn("/workspaces/velvet-codex:/workspace-base:ro", source)
        self.assertIn("/workspaces/max-codex:/workspace-base:ro", source)
        self.assertIn("CODEX_WORKSPACE_BASE: /workspace-base", source)
        self.assertIn(
            "CODEX_ISOLATED_WORKSPACE_ROOT: /opt/codex-runs/workspaces", source
        )
        self.assertNotIn("/workspaces/velvet-codex:/workspace\n", source)
        self.assertNotIn("/workspaces/max-codex:/workspace\n", source)
        self.assertNotIn("/srv/velvet:/workspace", source)
        self.assertNotIn("/srv/romatic-club:/workspace", source)
        self.assertNotIn("docker.sock", source)

    def test_codex_runners_have_only_egress_and_agent_control(self) -> None:
        source = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        velvet = source.split("  hermes-coder-velvet:", 1)[1].split(
            "\n  max-db-proxy:", 1
        )[0]
        maximum = source.split("  hermes-coder-max:", 1)[1].split(
            "\nnetworks:", 1
        )[0]
        codex_anchor = source.split("x-codex-runner: &codex-runner", 1)[1].split(
            "\nx-db-proxy:", 1
        )[0]
        self.assertIn("read_only: true", codex_anchor)
        self.assertIn("working_dir: /opt/codex-runs", codex_anchor)
        for section in (velvet, maximum):
            self.assertIn("<<: *codex-runner", section)
            self.assertIn("- egress", section)
            self.assertIn("- agent-control", section)
            self.assertIn(":/workspace-base:ro", section)
            self.assertNotIn("velvet-db", section)
            self.assertNotIn("max-db", section)
            self.assertNotIn("velvet-production", section)
            self.assertNotIn("max-production", section)

    def test_chat_gateways_keep_read_only_database_routes(self) -> None:
        source = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        velvet = source.split("  hermes-chat-velvet:", 1)[1].split(
            "\n  hermes-coder-velvet:", 1
        )[0]
        maximum = source.split("  hermes-chat-max:", 1)[1].split(
            "\n  hermes-coder-max:", 1
        )[0]
        self.assertIn("- velvet-db", velvet)
        self.assertIn("- max-db", maximum)
        self.assertNotIn("velvet-production", velvet)
        self.assertNotIn("max-production", maximum)

    def test_codex_model_set_and_default_are_fixed(self) -> None:
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        runner = (ROOT / "codex_runner.py").read_text(encoding="utf-8")
        self.assertIn("CODEX_DEFAULT_MODEL: gpt-5.6-terra", compose)
        self.assertIn(
            "CODEX_ALLOWED_MODELS: gpt-5.6-luna,gpt-5.6-terra,gpt-5.6-sol",
            compose,
        )
        for model in ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"):
            self.assertIn(model, runner)
        self.assertNotIn("gpt-5.3-codex-spark", runner)
        self.assertIn("model-capacity-only", runner)

    def test_codex_cli_is_pinned_and_digest_verified(self) -> None:
        source = (ROOT / "Dockerfile.coder").read_text(encoding="utf-8")
        self.assertIn("ARG CODEX_VERSION=0.144.1", source)
        self.assertIn("openai/codex/releases/tags/rust-v${CODEX_VERSION}", source)
        self.assertIn("sha256sum -c -", source)
        self.assertIn("ripgrep", source)
        self.assertIn("COPY --chmod=0555 codex_runner.py", source)

    def test_codex_auth_and_runner_keys_are_project_isolated(self) -> None:
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        installer = (ROOT / "install-codex.sh").read_text(encoding="utf-8")
        preflight = (ROOT / "preflight.py").read_text(encoding="utf-8")
        self.assertIn("/codex/velvet:/opt/codex", compose)
        self.assertIn("/codex/max:/opt/codex", compose)
        self.assertIn("CODEX_RUNNER_API_KEY", installer)
        self.assertIn("cli_auth_credentials_store = \"file\"", installer)
        self.assertIn(
            "Velvet и Max должны использовать разные CODEX_RUNNER_API_KEY",
            preflight,
        )
        self.assertIn("auth.json", preflight)
        self.assertIn("требуется 0600", preflight)

    def test_brain_context_is_compiled_installed_and_verified_per_project(self) -> None:
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        initial_installer = (ROOT / "install-codex.sh").read_text(encoding="utf-8")
        reconcile_installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        preflight = (ROOT / "preflight.py").read_text(encoding="utf-8")
        runner = (ROOT / "codex_runner.py").read_text(encoding="utf-8")
        self.assertIn("HOME: /opt/codex", compose)
        for installer in (initial_installer, reconcile_installer):
            self.assertIn("context_compiler.py", installer)
            self.assertIn("install_context_pack.py", installer)
            self.assertIn("verify_installed_context.py", installer)
            self.assertIn("velvet-coder", installer)
            self.assertIn("max-coder", installer)
        self.assertIn("--mode hermes", reconcile_installer)
        self.assertIn("--mode codex", reconcile_installer)
        self.assertIn('mode="codex"', preflight)
        self.assertIn('"--output-schema"', runner)
        self.assertIn("structured_output", runner)

    def test_codex_shell_policy_excludes_unneeded_secrets(self) -> None:
        installer = (ROOT / "install-codex.sh").read_text(encoding="utf-8")
        for secret in (
            "API_SERVER_KEY",
            "BYESU_HERMES_CODEX_API_KEY",
            "BYESU_HERMES_GPT_PRO_API_KEY",
            "CODEX_RUNNER_API_KEY",
            "DATABASE_URL",
            "PGPASSWORD",
            "TELEGRAM_BOT_TOKEN",
        ):
            self.assertIn(f'"{secret}"', installer)
        self.assertNotIn('"GH_TOKEN",', installer)

    def test_device_login_is_explicit_and_non_destructive(self) -> None:
        source = (ROOT / "codex-login.sh").read_text(encoding="utf-8")
        self.assertIn("login --device-auth", source)
        self.assertIn("login status", source)
        self.assertIn("auth.json", source)
        self.assertNotIn("cat /opt/codex/auth.json", source)
        self.assertNotIn("rm -rf", source)

    def test_runtime_smoke_covers_base_and_disposable_run_sandbox(self) -> None:
        source = (ROOT / "runtime_smoke.py").read_text(encoding="utf-8")
        for marker in (
            "hermes-chat-velvet",
            "hermes-coder-velvet",
            "codex login status",
            "0.144.1",
            "gpt-5.6-luna",
            "gpt-5.6-terra",
            "gpt-5.6-sol",
            "push --dry-run",
            "/workspace-base",
            "SandboxLauncherClient",
            "client.probe",
            "host-sandbox-launcher",
            "disposable-docker-container",
            "nested_bwrap",
            "hermes-codex-runner",
            "test ! -e /workspace",
        ):
            self.assertIn(marker, source)
        for forbidden in (
            "--ro-bind /workspace-base /workspace-base",
            '--bind "$probe" "$probe"',
            "bwrap --unshare-user",
            "unshare --user",
        ):
            self.assertNotIn(forbidden, source)

    def test_existing_hermes_byesu_route_remains_available_for_chat(self) -> None:
        source = (ROOT / "config.yaml").read_text(encoding="utf-8")
        self.assertIn("default: gpt-5.4-mini", source)
        self.assertIn("model: gpt-5.6-terra", source)
        self.assertIn("model: gpt-5.6-luna", source)
        self.assertNotIn("api_key:", source)
        self.assertIn("cwd: /workspace", source)

    def test_systemd_runs_security_preflight_before_compose(self) -> None:
        source = Path("deploy/systemd/hermes-coders.service").read_text(
            encoding="utf-8"
        )
        preflight = f"ExecStartPre=+/usr/bin/python3 {RELEASE_PREFIX}/preflight.py"
        sandbox_preflight = (
            f"ExecStartPre=+/usr/bin/python3 {RELEASE_PREFIX}/sandbox_preflight.py"
        )
        compose_start = (
            "ExecStart=/usr/bin/docker compose --profile velvet "
            "--profile max -f compose.yaml -f compose.runtime.yaml "
            "-f compose.security.yaml up -d --build --remove-orphans"
        )
        smoke = f"ExecStartPost=/usr/bin/python3 {RELEASE_PREFIX}/runtime_smoke.py"
        self.assertIn(f"WorkingDirectory={RELEASE_PREFIX}", source)
        self.assertIn(preflight, source)
        self.assertIn(sandbox_preflight, source)
        self.assertIn(compose_start, source)
        self.assertIn(smoke, source)
        self.assertNotIn("/srv/velvet/deploy/hermes-coders", source)
        self.assertLess(source.index(preflight), source.index(sandbox_preflight))
        self.assertLess(source.index(sandbox_preflight), source.index(compose_start))
        self.assertLess(source.index(compose_start), source.index(smoke))

    def test_python_and_bash_sources_parse(self) -> None:
        for path in (
            ROOT / "codex_runner.py",
            ROOT / "db_proxy.py",
            ROOT / "ensure_runtime_config.py",
            ROOT / "preflight.py",
            ROOT / "runtime_smoke.py",
            ROOT / "codex_tier_runner.py",
            ROOT / "codex_launcher_runner.py",
            ROOT / "sandbox_launcher_client.py",
            ROOT / "sandbox_entrypoint.py",
            ROOT / "sandbox_preflight.py",
            LAUNCHER_ROOT / "launcher_contract.py",
            LAUNCHER_ROOT / "launcher_runtime.py",
            LAUNCHER_ROOT / "launcher.py",
        ):
            with self.subTest(path=path):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("bash is unavailable")
        for path in (
            ROOT / "install.sh",
            ROOT / "install-codex.sh",
            ROOT / "codex-login.sh",
            ROOT / "release.sh",
            LAUNCHER_ROOT / "install.sh",
            Path("deploy/hermes-orchestration/install.sh"),
        ):
            with self.subTest(path=path):
                result = subprocess.run(
                    [bash, "-n", str(path)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()

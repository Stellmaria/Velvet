from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

INSTALLER = Path("deploy/hermes-coders/install.sh")
SYNC_MARKER = (
    'python3 - "$OPERATOR_ENV" "$CONTROL_OPERATOR_ENV" '
    '"$ROOT/secrets/velvet.env" "$ROOT/secrets/max.env" <<\'PY\'\n'
)


def _extract_secret_sync_script() -> str:
    source = INSTALLER.read_text(encoding="utf-8")
    start = source.index(SYNC_MARKER) + len(SYNC_MARKER)
    end = source.index("\nPY\n", start)
    return source[start:end]


def _write_env(path: Path, values: dict[str, str]) -> None:
    path.write_text(
        "".join(f"{name}={value}\n" for name, value in values.items()),
        encoding="utf-8",
    )


def _read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line or "=" not in raw_line:
            continue
        name, value = raw_line.split("=", 1)
        result[name] = value
    return result


class HermesCoderSecretRotationTests(unittest.TestCase):
    def _run_sync(
        self,
        *,
        source_values: dict[str, str],
        velvet_values: dict[str, str],
        max_values: dict[str, str],
    ) -> tuple[Path, dict[str, str], Path, dict[str, str]]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        source = root / "operator.env"
        operator = root / "control.env"
        velvet = root / "velvet.env"
        max_env = root / "max.env"

        _write_env(source, source_values)
        _write_env(operator, {"HERMES_OPS_CLIENT_TOKEN": "router-client-token-1234567890"})
        _write_env(velvet, velvet_values)
        _write_env(max_env, max_values)

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                _extract_secret_sync_script(),
                str(source),
                str(operator),
                str(velvet),
                str(max_env),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return velvet, _read_env(velvet), max_env, _read_env(max_env)

    def test_operator_codex_key_rotates_existing_project_keys(self) -> None:
        velvet_path, velvet, max_path, max_env = self._run_sync(
            source_values={"BYESU_HERMES_CODEX_API_KEY": "new-canonical-byesu-key"},
            velvet_values={
                "BYESU_HERMES_CODEX_API_KEY": "old-velvet-byesu-key",
                "TELEGRAM_BOT_TOKEN": "velvet-telegram-token",
                "TELEGRAM_ALLOWED_USERS": "1001",
                "GH_TOKEN": "velvet-github-token",
                "API_SERVER_KEY": "velvet-api-server-key",
                "CODEX_RUNNER_API_KEY": "velvet-runner-key",
                "HERMES_CODER_ROUTER_CLIENT_TOKEN": "velvet-router-token",
                "HERMES_SANDBOX_LAUNCHER_TOKEN": "velvet-launcher-token",
            },
            max_values={
                "BYESU_HERMES_CODEX_API_KEY": "old-max-byesu-key",
                "TELEGRAM_BOT_TOKEN": "max-telegram-token",
                "GH_TOKEN": "max-github-token",
                "API_SERVER_KEY": "max-api-server-key",
                "HERMES_CODER_ROUTER_CLIENT_TOKEN": "max-router-token",
                "HERMES_SANDBOX_LAUNCHER_TOKEN": "max-launcher-token",
            },
        )

        self.assertEqual("new-canonical-byesu-key", velvet["BYESU_HERMES_CODEX_API_KEY"])
        self.assertEqual("new-canonical-byesu-key", max_env["BYESU_HERMES_CODEX_API_KEY"])

        self.assertEqual("velvet-telegram-token", velvet["TELEGRAM_BOT_TOKEN"])
        self.assertEqual("velvet-github-token", velvet["GH_TOKEN"])
        self.assertEqual("velvet-api-server-key", velvet["API_SERVER_KEY"])
        self.assertEqual("velvet-runner-key", velvet["CODEX_RUNNER_API_KEY"])
        self.assertEqual("velvet-router-token", velvet["HERMES_CODER_ROUTER_CLIENT_TOKEN"])
        self.assertEqual("velvet-launcher-token", velvet["HERMES_SANDBOX_LAUNCHER_TOKEN"])

        self.assertEqual("max-telegram-token", max_env["TELEGRAM_BOT_TOKEN"])
        self.assertEqual("max-github-token", max_env["GH_TOKEN"])
        self.assertEqual("max-api-server-key", max_env["API_SERVER_KEY"])
        self.assertEqual("max-api-server-key", max_env["CODEX_RUNNER_API_KEY"])
        self.assertEqual("max-router-token", max_env["HERMES_CODER_ROUTER_CLIENT_TOKEN"])
        self.assertEqual("max-launcher-token", max_env["HERMES_SANDBOX_LAUNCHER_TOKEN"])

        self.assertEqual(0o600, velvet_path.stat().st_mode & 0o777)
        self.assertEqual(0o600, max_path.stat().st_mode & 0o777)

    def test_missing_operator_codex_key_preserves_existing_project_keys(self) -> None:
        _, velvet, _, max_env = self._run_sync(
            source_values={},
            velvet_values={"BYESU_HERMES_CODEX_API_KEY": "existing-velvet-key"},
            max_values={"BYESU_HERMES_CODEX_API_KEY": "existing-max-key"},
        )

        self.assertEqual("existing-velvet-key", velvet["BYESU_HERMES_CODEX_API_KEY"])
        self.assertEqual("existing-max-key", max_env["BYESU_HERMES_CODEX_API_KEY"])

    def test_generic_operator_aliases_do_not_rotate_hermes_codex_key(self) -> None:
        _, velvet, _, max_env = self._run_sync(
            source_values={
                "BYESU_HERMES_API_KEY": "legacy-alias-key",
                "OPENAI_API_KEY": "generic-openai-key",
            },
            velvet_values={"BYESU_HERMES_CODEX_API_KEY": "existing-velvet-key"},
            max_values={"BYESU_HERMES_CODEX_API_KEY": "existing-max-key"},
        )

        self.assertEqual("existing-velvet-key", velvet["BYESU_HERMES_CODEX_API_KEY"])
        self.assertEqual("existing-max-key", max_env["BYESU_HERMES_CODEX_API_KEY"])
        self.assertNotIn("BYESU_HERMES_API_KEY", velvet)
        self.assertNotIn("OPENAI_API_KEY", velvet)
        self.assertNotIn("BYESU_HERMES_API_KEY", max_env)
        self.assertNotIn("OPENAI_API_KEY", max_env)

    def test_media_key_rotates_only_velvet_and_is_removed_from_max(self) -> None:
        _, velvet, _, max_env = self._run_sync(
            source_values={"BYESU_HERMES_MEDIA_API_KEY": "new-media-key"},
            velvet_values={
                "BYESU_HERMES_CODEX_API_KEY": "velvet-codex-key",
                "BYESU_HERMES_MEDIA_API_KEY": "old-media-key",
            },
            max_values={
                "BYESU_HERMES_CODEX_API_KEY": "max-codex-key",
                "BYESU_HERMES_MEDIA_API_KEY": "stale-max-media-key",
            },
        )

        self.assertEqual("new-media-key", velvet["BYESU_HERMES_MEDIA_API_KEY"])
        self.assertNotIn("BYESU_HERMES_MEDIA_API_KEY", max_env)

    def test_missing_operator_media_key_preserves_existing_velvet_media_key(self) -> None:
        _, velvet, _, max_env = self._run_sync(
            source_values={},
            velvet_values={
                "BYESU_HERMES_CODEX_API_KEY": "velvet-codex-key",
                "BYESU_HERMES_MEDIA_API_KEY": "existing-media-key",
            },
            max_values={
                "BYESU_HERMES_CODEX_API_KEY": "max-codex-key",
            },
        )

        self.assertEqual("existing-media-key", velvet["BYESU_HERMES_MEDIA_API_KEY"])
        self.assertNotIn("BYESU_HERMES_MEDIA_API_KEY", max_env)


if __name__ == "__main__":
    unittest.main()

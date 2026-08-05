from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CODER_ROOT = REPO_ROOT / "deploy" / "hermes-coders"


def test_coder_runtime_exports_app_pythonpath_for_smoke_imports() -> None:
    runtime = (CODER_ROOT / "compose.runtime.yaml").read_text(encoding="utf-8")

    assert runtime.count("PYTHONPATH: /app") == 2
    assert runtime.count(
        "./sandbox_launcher_client.py:/app/sandbox_launcher_client.py:ro"
    ) == 2


def test_release_rollback_loads_launcher_environment() -> None:
    release = (CODER_ROOT / "release.sh").read_text(encoding="utf-8")

    rollback_start = release.index("rollback_compose=(")
    rollback_end = release.index(")", rollback_start)
    rollback_compose = release[rollback_start:rollback_end]

    assert '--env-file "$ROOT/launcher.env"' in rollback_compose
    assert "HERMES_SANDBOX_GID" in (
        CODER_ROOT / "compose.runtime.yaml"
    ).read_text(encoding="utf-8")


def test_canonical_release_shell_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(CODER_ROOT / "release.sh")],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr

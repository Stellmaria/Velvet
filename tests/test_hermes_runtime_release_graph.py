from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODER_ROOT = ROOT / "deploy/hermes-coders"


def _load_guard():
    path = CODER_ROOT / "runtime_source_guard.py"
    spec = importlib.util.spec_from_file_location("hermes_runtime_source_guard_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runtime_compose_mounts_complete_release_graph_for_both_coders() -> None:
    source = (CODER_ROOT / "compose.runtime.yaml").read_text(encoding="utf-8")

    for runtime_source in (
        "codex_runner.py",
        "codex_routed_runner.py",
        "codex_first_runner.py",
        "codex_first_safe_runner.py",
        "codex_provider_chain_runner.py",
        "codex_tier_runner.py",
    ):
        mount = f"./{runtime_source}:/app/{runtime_source}:ro"
        assert source.count(mount) == 2


def test_runtime_source_guard_covers_base_modules_and_import_graph() -> None:
    guard = _load_guard()

    assert "codex_runner.py" in guard.RUNTIME_SOURCES
    assert "codex_routed_runner.py" in guard.RUNTIME_SOURCES
    assert "HERMES_RUNTIME_IMPORT_GRAPH_OK" in guard._IMPORT_PROBE
    assert "codex_tier_runner" in guard._IMPORT_PROBE


def test_runtime_source_guard_accepts_repository_import_graph() -> None:
    result = subprocess.run(
        [sys.executable, str(CODER_ROOT / "runtime_source_guard.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "permissions and imports: OK" in result.stdout

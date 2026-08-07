from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODER_ROOT = ROOT / "deploy/hermes-coders"
SYSTEMD_UNIT = ROOT / "deploy/systemd/hermes-coders.service"


def _load_guard():
    path = CODER_ROOT / "runtime_source_guard.py"
    spec = importlib.util.spec_from_file_location("hermes_runtime_source_guard_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _runtime_python_mounts() -> set[str]:
    source = (CODER_ROOT / "compose.runtime.yaml").read_text(encoding="utf-8")
    mounts: set[str] = set()
    pattern = re.compile(r"^\s*-\s+\./([^:/]+\.py):/app/\1:ro\s*$")
    for line in source.splitlines():
        match = pattern.match(line)
        if match:
            mounts.add(match.group(1))
    return mounts


def test_runtime_compose_mounts_complete_release_graph_for_both_coders() -> None:
    source = (CODER_ROOT / "compose.runtime.yaml").read_text(encoding="utf-8")

    for runtime_source in (
        "codex_runner.py",
        "codex_routed_runner.py",
        "codex_first_runner.py",
        "codex_first_safe_runner.py",
        "codex_provider_chain_runner.py",
        "codex_tier_runner.py",
        "codex_image_runner.py",
        "byesu_image_fallback.py",
        "byesu_image_routing_policy.py",
        "codex_image_limit_preflight.py",
        "codex_image_high_res_export.py",
    ):
        mount = f"./{runtime_source}:/app/{runtime_source}:ro"
        assert source.count(mount) == 2


def test_every_runtime_python_mount_is_covered_by_permission_guard() -> None:
    guard = _load_guard()
    mounted_sources = _runtime_python_mounts()

    assert mounted_sources
    assert mounted_sources <= set(guard.RUNTIME_SOURCES)


def test_runtime_source_guard_covers_base_modules_and_import_graph() -> None:
    guard = _load_guard()

    assert "codex_runner.py" in guard.RUNTIME_SOURCES
    assert "codex_routed_runner.py" in guard.RUNTIME_SOURCES
    assert "codex_image_runner.py" in guard.RUNTIME_SOURCES
    assert "byesu_image_fallback.py" in guard.RUNTIME_SOURCES
    assert "byesu_image_routing_policy.py" in guard.RUNTIME_SOURCES
    assert "codex_image_limit_preflight.py" in guard.RUNTIME_SOURCES
    assert "codex_image_high_res_export.py" in guard.RUNTIME_SOURCES
    assert "HERMES_RUNTIME_IMPORT_GRAPH_OK" in guard._IMPORT_PROBE
    assert "codex_tier_runner" in guard._IMPORT_PROBE
    assert "codex_image_runner" in guard._IMPORT_PROBE
    assert "byesu_image_fallback" in guard._IMPORT_PROBE
    assert "byesu_image_routing_policy" in guard._IMPORT_PROBE
    assert "codex_image_limit_preflight" in guard._IMPORT_PROBE
    assert "codex_image_high_res_export" in guard._IMPORT_PROBE


def test_systemd_permission_preflight_covers_image_runners() -> None:
    unit = SYSTEMD_UNIT.read_text(encoding="utf-8")

    for runtime_source in (
        "codex_image_runner.py",
        "byesu_image_fallback.py",
        "byesu_image_routing_policy.py",
        "codex_image_limit_preflight.py",
        "codex_image_high_res_export.py",
    ):
        runtime_path = f"/deploy/hermes-coders/{runtime_source}"
        assert unit.count(runtime_path) == 2

    # Provider smoke is normalized twice and executed on start/reload.
    assert unit.count("/deploy/hermes-coders/image_provider_smoke.py") == 4


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


def test_canonical_release_preserves_images_and_removes_legacy_dropin() -> None:
    release = (CODER_ROOT / "release.sh").read_text(encoding="utf-8")

    assert "ROLLBACK_VELVET_TAG=" in release
    assert "ROLLBACK_MAX_TAG=" in release
    assert 'docker tag "$PREVIOUS_VELVET_IMAGE" "$ROLLBACK_VELVET_TAG"' in release
    assert 'docker tag "$PREVIOUS_MAX_IMAGE" "$ROLLBACK_MAX_TAG"' in release
    assert "refusing rollback recreation with incorrect local tags" in release
    assert "20-bwrap-runtime.conf" in release
    assert 'rm -f -- "$LEGACY_DROPIN"' in release


def test_canonical_release_uses_app_user_for_production_git_metadata() -> None:
    release = (CODER_ROOT / "release.sh").read_text(encoding="utf-8")

    assert 'APP_USER="${HERMES_CODERS_APP_USER:-velvet}"' in release
    assert 'runuser -u "$APP_USER" -- git -C "$APP_DIR" fetch' in release
    assert 'runuser -u "$APP_USER" -- git -C "$APP_DIR" rev-parse origin/main' in release
    assert "\ncd \"$APP_DIR\"\n" not in release
    assert "\ngit fetch --no-tags --prune origin main\n" not in release


def test_canonical_release_shell_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(CODER_ROOT / "release.sh")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr

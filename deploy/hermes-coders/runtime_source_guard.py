#!/usr/bin/env python3
from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent
RUNTIME_SOURCES = (
    "codex_delegate.py",
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
    "codex_launcher_runner.py",
    "codex_context_launcher_runner.py",
    "sandbox_launcher_client.py",
    "sandbox_preflight.py",
    "compose.runtime.yaml",
)
_IMPORT_PROBE = """
import sys
import types

# The guard executes with host Python before Docker Compose activation. Pillow is
# intentionally installed only in the coder image, so expose the smallest import
# stub required to validate our internal monkey-patch graph without widening the
# VPS Python dependency surface. Runtime/container smoke still imports real PIL.
pil = types.ModuleType("PIL")
pil_image = types.ModuleType("PIL.Image")
pil.Image = pil_image
sys.modules["PIL"] = pil
sys.modules["PIL.Image"] = pil_image

from codex_runner import Handler, ThreadingHTTPServer
import codex_routed_runner
import codex_first_runner
import codex_first_safe_runner
import codex_provider_chain_runner
import codex_tier_runner
import codex_image_runner
import byesu_image_fallback
import byesu_image_routing_policy
import codex_image_limit_preflight
import codex_image_high_res_export
import sandbox_launcher_client
import codex_launcher_runner
import codex_context_launcher_runner
assert codex_first_runner.Handler is Handler
assert codex_first_runner.ThreadingHTTPServer is ThreadingHTTPServer
assert codex_routed_runner.Handler is Handler
assert issubclass(codex_launcher_runner.LauncherTierProviderManager, codex_tier_runner.AuditedTierProviderManager)
assert issubclass(codex_context_launcher_runner.ContextLauncherTierProviderManager, codex_launcher_runner.LauncherTierProviderManager)
assert callable(byesu_image_fallback.install_byesu_image_fallback)
assert callable(byesu_image_routing_policy.install_byesu_image_routing_policy)
assert callable(codex_image_limit_preflight.install_codex_image_limit_preflight)
assert callable(codex_image_high_res_export.install_codex_image_high_res_export)
print("HERMES_RUNTIME_IMPORT_GRAPH_OK")
"""


class RuntimeSourceError(RuntimeError):
    pass


def ensure_runtime_sources_container_readable(root: Path = SOURCE_DIR) -> None:
    """Grant only the world-read bit required by bind-mounted container UIDs."""
    for name in RUNTIME_SOURCES:
        path = root / name
        if not path.is_file():
            raise RuntimeSourceError(f"Отсутствует runtime source: {path}")
        mode = stat.S_IMODE(path.stat().st_mode)
        readable_mode = mode | stat.S_IROTH
        if readable_mode != mode:
            path.chmod(readable_mode)


def validate_runtime_sources(root: Path = SOURCE_DIR) -> None:
    for name in RUNTIME_SOURCES:
        path = root / name
        if not path.is_file():
            raise RuntimeSourceError(f"Отсутствует runtime source: {path}")
        mode = stat.S_IMODE(path.stat().st_mode)
        if not mode & stat.S_IROTH:
            raise RuntimeSourceError(
                f"Bind-mounted runtime source недоступен container UID: {path} ({mode:04o})"
            )


def validate_runtime_import_graph(root: Path = SOURCE_DIR) -> None:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(root)
    result = subprocess.run(
        [sys.executable, "-c", _IMPORT_PROBE],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        details = (result.stderr.strip() or result.stdout.strip() or "unknown error")[-2000:]
        raise RuntimeSourceError(f"Несовместимый runtime import graph: {details}")


def main() -> int:
    ensure_runtime_sources_container_readable()
    validate_runtime_sources()
    validate_runtime_import_graph()
    print("Hermes coder runtime source permissions and imports: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeSourceError, subprocess.TimeoutExpired) as error:
        print(f"Hermes coder runtime source guard failed: {error}", file=sys.stderr)
        raise SystemExit(2)
